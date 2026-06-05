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
        self.stdout.write(self.style.WARNING("Iniciando a importação dos dados..."))

        # Caminho da pasta de arquivos
        csv_dir = os.path.join(os.getcwd(), "csv_data")

        if not os.path.exists(csv_dir):
            self.stdout.write(
                self.style.ERROR(
                    f"Pasta {csv_dir} não encontrada. Crie-a e coloque os arquivos lá."
                )
            )
            return

        # ----------------------------------------------------
        # 1. PROCESSANDO OS ARQUIVOS DAS MATÉRIAS TÉCNICAS
        # ----------------------------------------------------
        tech_files = glob.glob(os.path.join(csv_dir, "* - *.csv"))

        for file_path in tech_files:
            filename = os.path.basename(file_path)
            if "Mapão" in filename:
                continue  # O mapão tem estrutura diferente, tratamos depois

            # Descobrir o nome da disciplina extraindo a parte final do nome do arquivo
            subject_name = filename.split(" - ")[-1].replace(".csv", "").strip()
            subject, _ = Subject.objects.get_or_create(name=subject_name)

            self.stdout.write(
                self.style.SUCCESS(f"Processando matéria técnica: {subject_name}")
            )

            # Ler o CSV da matéria
            df = pd.read_csv(file_path)

            # Limpar nomes das colunas (remover quebras de linha que o Excel/Google gera)
            df.columns = [c.replace("\n", " ").strip() for c in df.columns]

            # Identificar colunas chaves
            col_nome = "Nome"
            col_situacao = "Situação"
            col_media = "Média"
            col_atividades = [c for c in df.columns if "Atividades" in c]
            col_trabalhos = [c for c in df.columns if "Trabalho" in c]
            col_provas = [c for c in df.columns if "Prova" in c and "Paulista" not in c]
            col_paulista = [c for c in df.columns if "Prova Paulista" in c]

            for _, row in df.iterrows():
                nome_aluno = str(row[col_nome]).strip()
                if not nome_aluno or nome_aluno == "nan" or nome_aluno.startswith(" "):
                    continue

                situacao = (
                    str(row[col_situacao]).strip()
                    if col_situacao in df.columns
                    else "Ativo"
                )

                # Criar ou atualizar o Aluno
                student, _ = Student.objects.get_or_create(
                    name=nome_aluno, defaults={"status": situacao}
                )

                # Coletar as notas tratadas
                obs = (
                    str(row[df.columns[-1]]).strip()
                    if pd.isna(row[df.columns[-1]]) == False
                    and str(row[df.columns[-1]]) != row[col_media]
                    else ""
                )

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
                        "final_average": (
                            str(row[col_media]) if col_media in df.columns else None
                        ),
                        "observation": obs,
                    },
                )

        # ----------------------------------------------------
        # 2. PROCESSANDO O MAPÃO (FALTAS E FREQUÊNCIAS GERAIS)
        # ----------------------------------------------------
        mapao_pattern = os.path.join(csv_dir, "* - Mapão.csv")
        mapao_files = glob.glob(mapao_pattern)

        if mapao_files:
            self.stdout.write(
                self.style.SUCCESS("Processando dados de Frequência Geral do Mapão...")
            )
            # O mapão possui metadados nas primeiras 9 linhas, pulamos para pegar o cabeçalho correto
            df_mapao = pd.read_csv(mapao_files[0], skiprows=9)

            # A primeira coluna representa o nome do Aluno
            first_col = df_mapao.columns[0]

            for _, row in df_mapao.iterrows():
                nome_aluno = str(row[first_col]).strip()
                # Validação para ignorar linhas de cabeçalhos repetidos ou rodapés
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

                # Procurar as colunas de fechamento que ficam lá no final do arquivo
                # Faltas Bimestre, % Freq Bimestre, Faltas Anual, % Freq Anual
                try:
                    # Buscando dinamicamente as últimas colunas de métricas de rendimento
                    last_cols = [
                        c
                        for c in df_mapao.columns
                        if "%" in str(c) or "Faltas" in str(c) or "Freq" in str(c)
                    ]

                    # Atualiza os dados de frequência do aluno no banco
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
                except Exception as e:
                    pass

        self.stdout.write(
            self.style.SUCCESS(
                "🎉 Todos os dados foram importados com sucesso para o PostgreSQL!"
            )
        )
