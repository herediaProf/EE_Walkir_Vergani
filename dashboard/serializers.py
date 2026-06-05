from rest_framework import serializers
from .models import Student, ComponentGradeDetail


class ComponentGradeDetailSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = ComponentGradeDetail
        fields = [
            "id",
            "subject_name",
            "activities",
            "assignments",
            "tests",
            "prova_paulista",
            "final_average",
            "observation",
        ]


class StudentDashboardSerializer(serializers.ModelSerializer):
    component_grades = ComponentGradeDetailSerializer(many=True, read_only=True)

    # Novos campos calculados em tempo real pela nossa IA Pedagógica
    ia_risk_level = serializers.SerializerMethodField()
    ia_diagnostic_report = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id",
            "name",
            "status",
            "frequency_pct",
            "frequency_pct_annual",
            "component_grades",
            "ia_risk_level",
            "ia_diagnostic_report",
        ]

    def get_ia_risk_level(self, obj):
        """
        Calcula o nível de risco do aluno cruzando frequência e notas baixas.
        """
        # Converter frequência para número limpo (ex: "94%" -> 94)
        try:
            freq_str = obj.frequency_pct_annual or obj.frequency_pct or "100"
            freq = float(freq_str.replace("%", "").strip())
        except ValueError:
            freq = 100.0

        # Se a frequência anual estiver abaixo de 75%, o risco é crítico por lei (Reprovação por faltas)
        if freq < 75.0:
            return "CRÍTICO (Frequência)"

        # Conta em quantas matérias o aluno está com menção/status de recuperação
        grades = obj.component_grades.all()
        subjects_in_recovery = 0

        for g in grades:
            # Analisa se a observação aponta recuperação ou se a média final é explicitamente baixa
            obs = str(g.observation or "").lower()
            avg_str = str(g.final_average or "").replace(",", ".")

            try:
                avg = float(avg_str) if avg_str and avg_str != "none" else 6.0
            except ValueError:
                avg = 6.0

            if "recuperação" in obs or avg < 5.0:
                subjects_in_recovery += 1

        if subjects_in_recovery >= 3:
            return "ALTO"
        elif subjects_in_recovery > 0:
            return "MÉDIO"

        return "BAIXO"

    def get_ia_diagnostic_report(self, obj):
        """
        Gera uma síntese pedagógica descritiva automatizada para o Conselho de Classe.
        """
        try:
            freq_str = obj.frequency_pct_annual or obj.frequency_pct or "100%"
            freq = float(freq_str.replace("%", "").strip())
        except ValueError:
            freq = 100.0

        grades = obj.component_grades.all()
        rec_subjects = []
        excellent_subjects = []

        for g in grades:
            sub_name = g.subject.name
            obs = str(g.observation or "").lower()
            avg_str = str(g.final_average or "").replace(",", ".")

            try:
                avg = float(avg_str) if avg_str and avg_str != "none" else 6.0
            except ValueError:
                avg = 6.0

            if "recuperação" in obs or avg < 5.0:
                rec_subjects.append(sub_name)
            elif avg >= 7.0:
                excellent_subjects.append(sub_name)

        # Início da montagem do parecer da IA
        if freq < 75.0:
            return f"Atenção imediata: Aluno com frequência acumulada de {freq_str}, abaixo do limite legal de 75%. Risco iminente de retenção por assiduidade, independente do rendimento técnico."

        if not rec_subjects:
            perfis = f"Desempenho plenamente satisfatório. Mantém assiduidade adequada ({freq_str})."
            if excellent_subjects:
                perfis += f" Apresenta excelente rendimento em componentes chave como: {', '.join(excellent_subjects)}."
            return perfis

        # Caso apresente dependências ou recuperações
        materias_lista = ", ".join(rec_subjects)
        if len(rec_subjects) >= 3:
            return f"Diagnóstico de Alerta Estrutural: Aluno apresenta dificuldades severas e concomitantes em {len(rec_subjects)} disciplinas técnicas ({materias_lista}). Requer plano integrado de apoio pedagógico e convocação de responsáveis para alinhamento estratégico."
        else:
            return f"Acompanhamento focado sugerido: Aluno demonstra bom engajamento geral ({freq_str}), porém necessita de reforço pontual nos seguintes componentes: {materias_lista}."
