import csv
import glob
import os
import re
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ComponentGradeDetail, Student, Subject
from .serializers import StudentDashboardSerializer


class StudentViewSet(viewsets.ReadOnlyModelViewSet):
    """Endpoint de API que permite ao Frontend (React/Vue) visualizar os dados dos alunos e notas."""

    queryset = Student.objects.all().order_by("name")
    serializer_class = StudentDashboardSerializer

    @action(detail=False, methods=["get"])
    def resumo_conselho(self, request):
        """Gera uma métrica rápida para os cards superiores do Dashboard com base na IA e Status"""
        # Vamos usar o ia_risk_level se você adicionou, ou manter o seu filtro de status
        total = self.get_queryset().count()

        # Alunos em Risco Crítico ou Alto identificados pela triagem
        em_risco = (
            self.get_queryset()
            .filter(status__icontains="recuperação")
            .count()
            # Se quiser usar o novo campo do script depois, mude para: .filter(ia_risk_level__in=["CRÍTICO", "ALTO"]).count()
        )
        retidos_faltas = self.get_queryset().filter(status__icontains="retido").count()

        return Response(
            {
                "total_alunos": total,
                "alunos_em_risco": em_risco,
                "alunos_retidos_faltas": retidos_faltas,
            }
        )

    @action(detail=False, methods=["post"])
    def importar_mapao(self, request):
        """Lê o arquivo CSV do Conselho dentro da pasta csv_data e atualiza o Banco de Dados para o Vue/React."""
        # 1. Localizar a pasta csv_data que vimos que está na raiz do seu projeto
        # Como as views ficam dentro de uma subpasta app, subimos um nível para achar a raiz
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pasta_csv = os.path.join(base_dir, "csv_data")
        arquivos_csv = glob.glob(os.path.join(pasta_csv, "*.csv"))

        if not arquivos_csv:
            return Response(
                {
                    "error": "Nenhum arquivo CSV encontrado dentro do diretório 'csv_data/'."
                },
                status=400,
            )

        # Selecionar o arquivo mais recente ou o primeiro encontrado na pasta
        caminho_arquivo = arquivos_csv[0]

        try:
            # Ler o CSV tratando codificação comum de planilhas Excel (UTF-8 com BOM)
            with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as file:
                linhas = list(csv.reader(file))

            # No seu arquivo, a linha do cabeçalho de matérias fica no índice 9
            cabecalho = linhas[9]

            # Mapeamento exato dos nomes compridos do seu arquivo para o seu modelo Subject
            disciplinas_foco = {
                "CARREIRA E COMPETENCIAS PARA O MERCADO DE TRABALHO": {
                    "slug": "Carreira",
                    "code": "9929",
                },
                "LOGICA E LINGUAGENS DE PROGRAMACAO": {
                    "slug": "Lógica",
                    "code": "9938",
                },
                "PROCESSOS DE DESENVOLVIMENTO DE SOFTWARE E METODOLOGIAS AGEIS": {
                    "slug": "Metodologias Ágeis",
                    "code": "51003",
                },
                "REDES DE COMPUTADORES E SEGURANÇA DA INFORMAÇAO NA NUVEM": {
                    "slug": "Redes & Nuvem",
                    "code": "51002",
                },
            }

            # Identificar dinamicamente as colunas do arquivo para cada matéria técnica
            indices_materias = {}
            for nome_completo, info in disciplinas_foco.items():
                # Pegar ou Criar a matéria correspondente no banco
                subject_obj, _ = Subject.objects.get_or_create(
                    code=info["code"], defaults={"name": info["slug"]}
                )

                for i, col in enumerate(cabecalho):
                    if nome_completo in col:
                        # No Mapão, a nota 'M' fica exatamente 1 coluna após o nome/Nº da matéria
                        indices_materias[subject_obj] = i + 1

            alunos_processados = 0

            # As linhas com dados dos alunos começam no índice 11 do seu arquivo
            for linha in linhas[11:]:
                if not linha or len(linha) < 2:
                    continue

                nome_aluno = linha[0].strip()
                situacao = linha[1].strip()

                # 💡 Regra de Negócio: Ignorar alunos com Baixa por Transferência, Remanejados, etc.
                if situacao != "Ativo":
                    continue

                # Capturar faltas totais acumuladas e frequências das últimas colunas
                # 'TF' é a antepenúltima, Fre An(%) é a última
                faltas_totais = int(linha[-4]) if linha[-4].isdigit() else 0
                freq_anual = linha[-1].strip() if linha[-1] else "100%"

                # Atualizar ou Criar o Aluno Ativo no banco
                aluno_obj, created = Student.objects.update_or_create(
                    name=nome_aluno,
                    defaults={
                        "status": situacao,
                        "total_absences": faltas_totais,
                        "frequency_pct_annual": freq_anual,
                        # Se você tiver a coluna de porcentagem normal, adicione aqui
                    },
                )

                # Processar as Notas do Aluno para cada disciplina técnica mapeada
                soma_notas = 0
                qtd_notas = 0

                for subject_obj, idx_nota in indices_materias.items():
                    nota_bruta = linha[idx_nota].strip()

                    try:
                        nota_final = float(nota_bruta.replace(",", "."))
                    except ValueError:
                        nota_final = 0.0  # Se não houver nota lançada (-), define 0.0 para monitoramento

                    soma_notas += nota_final
                    qtd_notas += 1

                    # Define um parecer diagnóstico simples baseado no rendimento da nota
                    obs = "Rendimento Regular"
                    if nota_final < 5.0:
                        obs = "Necessita de Recuperação Urgente"
                    elif nota_final >= 8.0:
                        obs = "Excelente Desempenho Técnico"

                    # Gravar o detalhe da nota no banco de dados vinculando Aluno e Matéria
                    ComponentGradeDetail.objects.update_or_create(
                        student=aluno_obj,
                        subject=subject_obj,
                        defaults={"final_average": nota_final, "observation": obs},
                    )

                # Regra dinâmica opcional para injetar no campo observação do aluno
                media_geral_ds = soma_notas / qtd_notas if qtd_notas > 0 else 0
                if media_geral_ds < 5.0:
                    aluno_obj.status = "Em Recuperação"
                    aluno_obj.save()

                alunos_processados += 1

            return Response(
                {
                    "status": "sucesso",
                    "mensagem": f"{alunos_processados} alunos ativos e suas notas técnicas foram importados com sucesso!",
                }
            )

        except Exception as e:
            return Response(
                {
                    "error": "Falha ao processar a estrutura do arquivo Mapão.",
                    "details": str(e),
                },
                status=500,
            )
