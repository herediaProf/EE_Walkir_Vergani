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
)


class StudentViewSet(viewsets.ModelViewSet):
    """
    Endpoint completo (CRUD) para gerenciar alunos e gerar inteligência analítica para o Dashboard.
    """

    # Otimização N+1 para carregar tudo de forma super rápida em memória
    queryset = (
        Student.objects.all()
        .prefetch_related("component_grades__subject")
        .order_by("name")
    )
    serializer_class = StudentDashboardSerializer

    @action(detail=False, methods=["get"])
    def resumo_conselho(self, request):
        """Gera métricas rápidas para os cartões superiores do painel baseando-se nos dados reais."""
        total = Student.objects.count()
        # Conta alunos que possuem qualquer disciplina em situação de recuperação
        em_risco = (
            Student.objects.filter(
                component_grades__observation__icontains="recuperação"
            )
            .distinct()
            .count()
        )
        retidos = Student.objects.filter(status__icontains="retido").count()

        return Response(
            {
                "total_alunos": total,
                "alunos_em_risco": em_risco,
                "alunos_retidos_faltas": retidos,
            }
        )

    @action(detail=False, methods=["get"])
    def dashboard_analitico(self, request):
        """
        📊 Retorna dados estruturados e limpos para alimentar os gráficos do Vue (Pizza, Barras e Alertas).
        Calculado via Python para total segurança de tipos no PostgreSQL.
        """
        # 1. Gráfico de Pizza: Classificação Dinâmica de Risco por Frequência e Faltas
        alunos = Student.objects.all()
        baixo_risco = 0
        medio_risco = 0
        alto_risco = 0

        for aluno in alunos:
            try:
                freq_str = aluno.frequency_pct_annual or "100%"
                freq_val = float(freq_str.replace("%", "").strip().replace(",", "."))
            except ValueError:
                freq_val = 100.0

            # Regra de negócio: Frequência abaixo de 75% ou muitas faltas = Risco Alto
            if freq_val < 75.0 or aluno.total_absences > 20:
                alto_risco += 1
            elif freq_val < 85.0 or aluno.total_absences > 10:
                medio_risco += 1
            else:
                baixo_risco += 1

        grafico_pizza_risco = [
            {"ia_risk_level": "BAIXO", "total": baixo_risco},
            {"ia_risk_level": "MÉDIO", "total": medio_risco},
            {"ia_risk_level": "ALTO", "total": alto_risco},
        ]

        # 2. Gráfico de Barras: Média Real de Notas por Disciplina Técnica
        grades = ComponentGradeDetail.objects.select_related("subject").all()
        materia_dados = {}

        for g in grades:
            nome_materia = g.subject.name
            if not g.final_average:
                continue
            try:
                nota = float(g.final_average.replace(",", "."))
                if nome_materia not in materia_dados:
                    materia_dados[nome_materia] = []
                materia_dados[nome_materia].append(nota)
            except ValueError:
                continue

        grafico_barras_materias = []
        for nome_materia, lista_notas in materia_dados.items():
            media = sum(lista_notas) / len(lista_notas) if lista_notas else 0
            grafico_barras_materias.append(
                {"nome_materia": nome_materia, "media_geral": round(media, 2)}
            )

        # Ordena as matérias da maior média para a menor
        grafico_barras_materias.sort(key=lambda x: x["media_geral"], reverse=True)

        # 3. Alerta de Evasão Escolar: Top 5 alunos com mais faltas acumuladas
        alertas_evasao = (
            Student.objects.all()
            .order_by("-total_absences")[:5]
            .values("id", "name", "total_absences", "frequency_pct_annual", "status")
        )

        return Response(
            {
                "grafico_pizza_risco": grafico_pizza_risco,
                "grafico_barras_materias": grafico_barras_materias,
                "alerta_evasao_top5": list(alertas_evasao),
            }
        )

    @action(detail=False, methods=["post"])
    def importar_mapao(self, request):
        """Lê o arquivo CSV do Conselho dentro da pasta csv_data e atualiza o Banco de dados."""
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

            cabecalho = linhas[9]

            disciplinas_foco = {
                "CARREIRA E COMPETENCIAS PARA O MERCADO DE TRABALHO": {
                    "slug": "Carreira",
                    "code": "9929",
                },
                "LOGICA E LINGUAGENS DE PROGRAMACAO": {
                    "slug": "lógica",
                    "code": "9938",
                },
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

            for linha in lines_row in linhas[11:]:
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

                for subject_obj, idx_nota in indices_materias.items():
                    if idx_nota >= len(linha):
                        continue

                    nota_bruta = linha[idx_nota].strip()

                    try:
                        nota_final = float(nota_bruta.replace(",", "."))
                        nota_str = str(nota_final).replace(".", ",")
                    except ValueError:
                        nota_str = None  # Salva nulo perfeitamente se a matéria não tiver nota lançada

                    obs = ""
                    if nota_str and float(nota_str.replace(",", ".")) < 5.0:
                        obs = "recuperação"

                    ComponentGradeDetail.objects.update_or_create(
                        student=aluno_obj,
                        subject=subject_obj,
                        defaults={"final_average": nota_str, "observation": obs},
                    )

                alunos_processados += 1

            return Response(
                {
                    "status": "sucesso",
                    "mensagem": f"{alunos_processados} alunos sincronizados com sucesso!",
                }
            )

        except Exception as e:
            return Response(
                {
                    "error": "Erro no processamento interno do arquivo",
                    "details": str(e),
                },
                status=500,
            )


class ComponentGradeDetailViewSet(viewsets.ModelViewSet):
    """
    Endpoint COMPLETO (CRUD) para gerenciar as notas diretamente (Editar, Atualizar, Deletar)
    """

    queryset = ComponentGradeDetail.objects.all()
    from .serializers import ComponentGradeDetailSerializer

    serializer_class = ComponentGradeDetailSerializer
