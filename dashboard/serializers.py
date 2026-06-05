from rest_framework import serializers
from .models import Student, Subject, ComponentGradeDetail


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = "__all__"


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
    # Traz os detalhes de notas de todas as matérias técnicas do aluno de uma só vez
    component_grades = ComponentGradeDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Student
        fields = [
            "id",
            "name",
            "status",
            "total_absences",
            "frequency_pct",
            "total_absences_annual",
            "frequency_pct_annual",
            "component_grades",
        ]
