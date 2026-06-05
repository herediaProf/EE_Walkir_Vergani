import os
import glob
import pandas as pd
from django.core.management.base import BaseCommand
from dashboard.models import Student, Subject, SubjectMetric, ComponentGradeDetail


class Command(BaseCommand):
    help = (
        "Lê e importa automaticamente os dados dos arquivos CSV para o banco PostgreSQL"
    )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING("Iniciando a importação robusta dos dados...")
        )

        csv_dir = os.path.join(os.getcwd(), "csv_data")

        if not os.path.exists(csv_dir):
            self.stdout.write(self.style.ERROR(f"Pasta {csv_dir} não encontrada."))
            return

        tech_files = glob.glob(os.path.join(csv_dir, "*.csv"))

        for file_path in tech_files:
            filename = os.path.basename(file_path)

            # Pula o arquivo do Mapão neste primeiro loop pois ele possui estrutura de matriz complexa
            if "Mapão" in filename:
                continue

            self.stdout.write(self.style.SUCCESS(f"Lendo arquivo: {filename}"))

            try:
                # Ler o CSV de forma flexível
                df = pd.read_csv(file_path)
                df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]

                # Descobrir dinamicamente qual coluna guarda o nome do aluno
                col_nome = None
                for c in df.columns:
                    if str(c).upper() in [
                        "NOME",
                        "ALUNO",
                        "NOME DO ALUNO",
                        "NOME_ALUNO",
                    ]:
                        col_nome = c
                        break

                # Se não achou uma palavra-chave clara, tenta usar a 3ª coluna (índice 2) ou a 1ª
                if not col_nome:
                    if len(df.columns) > 2:
                        col_nome = df.columns[2]
                    else:
                        col_nome = df.columns[0]

                # Descobrir coluna da Situação/Status
                col_situacao = None
                for c in df.columns:
                    if "SITUAÇÃO" in str(c).upper() or "STATUS" in str(c).upper():
                        col_situacao = c
                        break

                # Descobrir coluna de Média Final
                col_media = None
                for c in df.columns:
                    if "MÉDIA" in str(c).upper() or "MEDIA" in str(c).upper():
                        col_media = c
                        break

                # Buscar colunas de avaliações individuais
                col_atividades = [
                    c for c in df.columns if "ATIVIDADE" in str(c).upper()
                ]
                col_trabalhos = [c for c in df.columns if "TRABALHO" in str(c).upper()]
                col_provas = [
                    c
                    for c in df.columns
                    if "PROVA" in str(c).upper() and "PAULISTA" not in str(c).upper()
                ]
                col_paulista = [c for c in df.columns if "PAULISTA" in str(c).upper()]

                # Definir o nome da disciplina com base no nome do arquivo
                if " - " in filename:
                    subject_name = filename.split(" - ")[-1].replace(".csv", "").strip()
                else:
                    subject_name = filename.replace(".csv", "").strip()

                # Ignorar arquivos genéricos de lista pura se houver
                if subject_name.upper() in ["ALUNOS2C", "LISTA", "ALUNOS"]:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Arquivo '{filename}' identificado como lista base. Sincronizando apenas nomes dos alunos."
                        )
                    )
                    for _, row in df.iterrows():
                        nome_aluno = str(row[col_nome]).strip()
                        if (
                            nome_aluno
                            and nome_aluno != "nan"
                            and not nome_aluno.startswith(" ")
                        ):
                            situacao = (
                                str(row[col_situacao]).strip()
                                if col_situacao
                                else "Ativo"
                            )
                            Student.objects.get_or_create(
                                name=nome_aluno, defaults={"status": situacao}
                            )
                    continue

                # Cria a Disciplina se não existir
                subject, _ = Subject.objects.get_or_create(name=subject_name)

                # Processar as linhas das notas técnicas
                for _, row in df.iterrows():
                    nome_aluno = str(row[col_nome]).strip()
                    if (
                        not nome_aluno
                        or nome_aluno == "nan"
                        or nome_aluno.startswith(" ")
                        or "Aulas" in nome_aluno
                    ):
                        continue

                    situacao = (
                        str(row[col_situacao]).strip() if col_situacao else "Ativo"
                    )

                    # Garantir que o aluno existe no banco
                    student, _ = Student.objects.get_or_create(
                        name=nome_aluno, defaults={"status": situacao}
                    )

                    # Trata observações finais da linha
                    obs = ""
                    if len(df.columns) > 0:
                        last_val = str(row[df.columns[-1]]).strip()
                        if (
                            last_val
                            and last_val != "nan"
                            and last_val != str(row.get(col_media, ""))
                        ):
                            obs = last_val

                    # Salvar ou atualizar os detalhes de notas
                    ComponentGradeDetail.objects.update_or_create(
                        student=student,
                        subject=subject,
                        defaults={
                            "activities": (
                                str(row[col_atividades[0]]) if col_atividades else None
                            ),
                            "assignments": (
                                str(row[col_trabalhos[0]]) if col_trabalhos else None
                            ),
                            "tests": str(row[col_provas[0]]) if col_provas else None,
                            "prova_paulista": (
                                str(row[col_paulista[0]]) if col_paulista else None
                            ),
                            "final_average": str(row[col_media]) if col_media else None,
                            "observation": obs,
                        },
                    )
            except Exception as err:
                self.stdout.write(
                    self.style.ERROR(
                        f"Aviso: Erro ao ler dados técnicos de {filename}: {err}. Pulando registro."
                    )
                )

        # ----------------------------------------------------
        # 2. PROCESSANDO O MAPÃO (FALTAS E FREQUÊNCIAS GERAIS)
        # ----------------------------------------------------
        mapao_files = glob.glob(os.path.join(csv_dir, "* - Mapão.csv"))
        if mapao_files:
            self.stdout.write(
                self.style.SUCCESS("Processando dados consolidados do Mapão...")
            )
            try:
                df_mapao = pd.read_csv(mapao_files[0], skiprows=9)
                first_col = df_mapao.columns[0]

                for _, row in df_mapao.iterrows():
                    nome_aluno = str(row[first_col]).strip()
                    if (
                        not nome_aluno
                        or nome_aluno in ["nan", "ALUNO", ""]
                        or "Aulas Dadas" in nome_aluno
                    ):
                        continue

                    situacao = (
                        str(row["SITUAÇÃO"]).strip()
                        if "SITUAÇÃO" in df_mapao.columns
                        else "Ativo"
                    )

                    # Atualiza com tolerância a índices as últimas colunas de frequência geral
                    try:
                        Student.objects.filter(name=nome_aluno).update(
                            status=situacao,
                            frequency_pct=(
                                str(row[df_mapao.columns[-3]])
                                if len(df_mapao.columns) > 3
                                else "100%"
                            ),
                            frequency_pct_annual=(
                                str(row[df_mapao.columns[-1]])
                                if len(df_mapao.columns) > 1
                                else "100%"
                            ),
                        )
                    except:
                        pass
            except Exception as err:
                self.stdout.write(
                    self.style.ERROR(f"Erro ao processar Mapão geral: {err}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                "🎉 Sincronização robusta finalizada com sucesso no PostgreSQL!"
            )
        )
