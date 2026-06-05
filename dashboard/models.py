from django.db import models


class Student(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Nome do Aluno")
    status = models.CharField(max_length=50, verbose_name="Situação")
    total_absences = models.IntegerField(
        default=0, verbose_name="Total Faltas Bimestre"
    )
    frequency_pct = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Frequência Bimestre"
    )
    total_absences_annual = models.IntegerField(
        default=0, verbose_name="Total Faltas Anual"
    )
    frequency_pct_annual = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Frequência Anual"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Aluno"
        verbose_name_plural = "Alunos"


class Subject(models.Model):
    name = models.CharField(
        max_length=255, unique=True, verbose_name="Nome da Disciplina"
    )
    code = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="Código da Disciplina"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Disciplina"
        verbose_name_plural = "Disciplinas"


class SubjectMetric(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="metrics"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="metrics"
    )
    average_grade = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Média"
    )
    absences = models.IntegerField(default=0, verbose_name="Faltas")
    compensated_lessons = models.IntegerField(
        default=0, verbose_name="Aulas Compensadas"
    )

    def __str__(self):
        return f"{self.student.name} - {self.subject.name}"

    class Meta:
        verbose_name = "Métrica de Disciplina"
        verbose_name_plural = "Métricas das Disciplinas"


class ComponentGradeDetail(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="component_grades"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="component_grades"
    )
    activities = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Atividades"
    )
    assignments = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Trabalhos"
    )
    tests = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Provas"
    )
    prova_paulista = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Prova Paulista"
    )
    final_average = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Média Final"
    )
    observation = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Observação/Situação"
    )

    def __str__(self):
        return f"Detalhe: {self.student.name} - {self.subject.name}"

    class Meta:
        verbose_name = "Detalhe de Nota Técnica"
        verbose_name_plural = "Detalhes de Notas Técnicas"
