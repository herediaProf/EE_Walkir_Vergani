import csv
import glob
import os
import re
from django.db.models import Count, Avg, F
from django.db.models.functions import Cast
from django.db import models
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

    # 🏎️ Otimização N+1: Traz tudo em 2 queries com JOIN na memória
    queryset = (
        Student.objects.all()
        .prefetch_related("component_grades__subject")
        .order_by("name")
    )
    serializer_class = StudentDashboardSerializer

    @action(detail=False, methods=["get"])
    def resumo_conselho(self, request):
        """Gera métricas rápidas para os cartões superiores do painel usando agregação nativa."""
        # Agregação unificada para evitar 3 COUNTs separados no banco
        metricas = Student.objects.aggregate(
            total=Count("id"),
            em_risco=Count(
                "id",
                filter=models.Q(status__icontains="recuperação")
                | models.Q(ia_risk_level__in=["CRÍTICO", "ALTO"]),
            ),
            retidos=Count("id", filter=models.Q(status__icontains="retido")),
        )
        return Response(
            {
                "total_alunos": metricas["total"],
                "alunos_em_risco": metricas["em_risco"],
                "alunos_retidos_faltas": metricas["retidos"],
            }
        )

    @action(detail=False, methods=["get"])
    def dashboard_analitico(self, request):
        """
        📊 NOVO: Retorna dados estruturados para alimentar os gráficos do Vue (Pizza, Barras e Alertas).
        """
        # 1. Gráfico de Pizza: Distribuição de Risco Computada pela IA
        distribuicao_risco = (
            Student.objects.values("ia_risk_level")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        # 2. Gráfico de Barras: Média de Notas por Disciplina Técnica
        # Como final_average é CharField ("7,1"), convertemos dinamicamente para Float para calcular a média real
        notas_convertidas = ComponentGradeDetail.objects.annotate(
            nota_float=Cast(
                models.functions.Replace(
                    F("final_average"), models.Value(","), models.Value(".")
                ),
                output_field=models.FloatField(),
            )
        )

        medias_por_disciplina = (
            notas_convertidas.values(nome_materia=F("subject__name"))
            .annotate(media_geral=Avg("nota_float"))
            .order_by("-media_geral")
        )

        # 3. Alerta de Evasão Escolar: Top 5 alunos com mais faltas acumuladas
        alertas_evasao = (
            Student.objects.all()
            .order_by("-total_absences")[:5]
            .values("id", "name", "total_absences", "frequency_pct_annual", "status")
        )

        return Response(
            {
                "grafico_pizza_risco": distribuicao_risco,
                "grafico_barras_materias": medias_por_disciplina,
                "alerta_evasao_top5": alertas_evasao,
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

            # Corrigido atribuição duplicada redundante (cabecalho = lines = linhas[9])
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
                    if idx_nota >= len(linha):
                        continue

                    nota_bruta = linha[idx_nota].strip()

                    try:
                        nota_final = float(nota_bruta.replace(",", "."))
                        nota_str = str(nota_final).replace(".", ",")
                        soma_notas += nota_final
                        qtd_notas += 1
                    except ValueError:
                        nota_str = None  # Deixa nulo se não houver nota no CSV (ex: Lógica sem nota)

                    obs = ""
                    if nota_str and float(nota_str.replace(",", ".")) < 5.0:
                        obs = "recuperação"

                    ComponentGradeDetail.objects.update_or_create(
                        student=aluno_obj,
                        subject=subject_obj,
                        defaults={"final_average": nota_str, "observation": obs},
                    )

                # 🤖 Recalcula o nível de risco de IA dinamicamente se o aluno estiver sem notas ou abaixo da média
                if qtd_notas > 0:
                    media_geral = soma_notas / qtd_notas
                    if media_geral < 5.0:
                        aluno_obj.ia_risk_level = "CRÍTICO"
                        aluno_obj.ia_diagnostic_report = f"Atenção: Aluno com média técnica insuficiente ({media_geral:.1f}). Necessita de rebatimento."
                        aluno_obj.save()

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
    Endpoint 🔓 COMPLETO (CRUD) para gerenciar as notas diretamente (Editar, Atualizar, Deletar)
    """

    queryset = ComponentGradeDetail.objects.all()
    from .serializers import ComponentGradeDetailSerializer

    serializer_class = ComponentGradeDetailSerializer
