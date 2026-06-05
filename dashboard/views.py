from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Student
from .serializers import StudentDashboardSerializer


class StudentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint de API que permite ao Frontend (React/Vue) visualizar os dados dos alunos e notas.
    """

    queryset = Student.objects.all().order_by("name")
    serializer_class = StudentDashboardSerializer

    @action(detail=False, methods=["get"])
    def resumo_conselho(self, request):
        """
        Gera uma métrica rápida para os cards superiores do Dashboard
        """
        total = self.get_queryset().count()
        em_recuperacao = (
            self.get_queryset().filter(status__icontains="recuperação").count()
        )
        retidos_faltas = self.get_queryset().filter(status__icontains="retido").count()

        return Response(
            {
                "total_alunos": total,
                "alunos_em_risco": em_recuperacao,
                "alunos_retidos_faltas": retidos_faltas,
            }
        )
