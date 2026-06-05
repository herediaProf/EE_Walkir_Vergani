from django.contrib import admin
from .models import Student, Subject, SubjectMetric, ComponentGradeDetail


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "total_absences",
        "frequency_pct",
        "frequency_pct_annual",
    )
    search_fields = ("name",)
    list_filter = ("status",)


class SubjectMetricInline(admin.TabularInline):
    model = SubjectMetric
    extra = 0


class ComponentGradeDetailInline(admin.TabularInline):
    model = ComponentGradeDetail
    extra = 0


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(SubjectMetric)
class SubjectMetricAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "subject",
        "average_grade",
        "absences",
        "compensated_lessons",
    )
    list_filter = ("subject",)
    search_fields = ("student__name", "subject__name")


@admin.register(ComponentGradeDetail)
class ComponentGradeDetailAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "final_average", "observation")
    list_filter = ("subject", "observation")
    search_fields = ("student__name", "subject__name")
