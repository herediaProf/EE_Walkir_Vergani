import csv
import glob
import os
import re
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ComponentGradeDetail, Student, Subject
from .serializers import (
    StudentDashboardSerializer,
    ComponentGradeDetailSerializer,
)  # <-- Certifique-se de ter esse serializer se o Vue for ler direto


class StudentViewSet(
    viewsets.ModelViewSet
):  # 🔓 Mudado de ReadOnlyModelViewSet para ModelViewSet
    """
    Endpoint completo (CRUD) para visualizar, editar, atualizar e deletar alunos.
    """

    queryset = Student.objects.all().order_by("name")
    serializer_class = StudentDashboardSerializer

    @action(detail=False, methods=["get"])
    def resumo_conselho(self, request):
        """Gera uma métrica rápida para os cards superiores do Dashboard com base na IA e Status"""
        total = self.get_queryset().count()
        em_risco = self.get_queryset().filter(status__icontains="recuperação").count()
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
        """Lê o arquivo CSV do Conselho dentro da pasta csv_data e atualiza o Banco."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pasta_csv = os.path.join(base_dir, "csv_data")
        arquivos_csv = glob.glob(os.path.join(pasta_csv, "*.csv"))

        if not arquivos_csv:
            return Response(
                {"error": "Nenhum arquivo CSV encontrado em 'csv_data/'."}, status=400
            )

        caminho_arquivo = arquivos_csv[0]

        try:
            with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as file:
                linhas = list(csv.reader(file))

            cabecalho = lines = linhas[9]

            disciplinas_foco = {
                "CARREIRA E COMPETENCIAS PARA O MERCADO DE TRABALHO": {
                    "slug": "Carreira",
                    "code": "9929",
                },
                "LOGICA E LINGUAGENS DE PROGRAMACAO": {
                    "slug": "lógica",
                    "code": "9938",
                },  # 💡 Padronizado minúsculo igual ao seu banco
                "PROCESSOS DE DESENVOLVIMENTO DE SOFTWARE E METODOLOGIAS AGEIS": {
                    "slug": "Ágeis",
                    "code": "51003",
                },
                "REDES DE COMPUTADORES E SEGURANÇA DA INFORMAÇAO NA NUVEM": {
                    "slug": "Redes",
                    "code": "51002",
                },
            }

            indices_materias = {}
            for nome_completo, info in disciplinas_foco.items():
                subject_obj, _ = Subject.objects.get_or_create(
                    code=info["code"], defaults={"name": info["slug"]}
                )
                for i, col in enumerate(cabecalho):
                    if nome_completo in col:
                        indices_materias[subject_obj] = i + 1

            alunos_processados = 0

            for linha in linhas[11:]:
                if not linha or len(linha) < 2:
                    continue

                nome_aluno = linha[0].strip().upper()
                situacao = linha[1].strip()

                if re.match(r"^\d+$", nome_aluno) or situacao != "Ativo":
                    continue

                faltas_totais = int(linha[-4]) if linha[-4].isdigit() else 0
                freq_anual = linha[-1].strip() if linha[-1] else "100%"

                aluno_obj, created = Student.objects.update_or_create(
                    name=nome_aluno,
                    defaults={
                        "status": situacao,
                        "total_absences": faltas_totais,
                        "frequency_pct_annual": freq_anual,
                    },
                )

                soma_notas = 0
                qtd_notas = 0

                for subject_obj, idx_nota in indices_materias.items():
                    nota_bruta = linha[idx_nota].strip()

                    try:
                        nota_final = float(nota_bruta.replace(",", "."))
                        nota_str = str(nota_final).replace(".", ",")
                    except ValueError:
                        nota_str = None  # Deixa nulo se não houver nota no CSV, para o professor editar no Vue

                    if nota_str:
                        soma_notas += float(nota_str.replace(",", "."))
                        qtd_notas += 1

                    obs = ""
                    if nota_str and float(nota_str.replace(",", ".")) < 5.0:
                        obs = "recuperação"

                    # Grava ou atualiza a nota
                    ComponentGradeDetail.objects.update_or_create(
                        student=aluno_obj,
                        subject=subject_obj,
                        defaults={"final_average": nota_str, "observation": obs},
                    )

                alunos_processados += 1

            return Response(
                {
                    "status": "sucesso",
                    "mensagem": f"{alunos_processados} alunos sincronizados!",
                }
            )

        except Exception as e:
            return Response(
                {"error": "Erro no processamento", "details": str(e)}, status=500
            )


class ComponentGradeDetailViewSet(viewsets.ModelViewSet):
    """
    Endpoint 🔓 COMPLETO (CRUD) para gerenciar as notas diretamente (Editar, Atualizar, Deletar)
    """

    queryset = ComponentGradeDetail.objects.all()
    # Se você já tiver um serializer para as notas, use-o aqui. Caso contrário, garanta que ele exista.
    from .serializers import ComponentGradeDetailSerializer

    serializer_class = ComponentGradeDetailSerializer
