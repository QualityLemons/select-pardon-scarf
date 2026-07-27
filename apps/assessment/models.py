from django.db import models
from django.conf import settings


class Module(models.Model):
    MODULE_TYPES = [
        ('challenge', 'Challenge'),
        ('lesson', 'Lesson'),
        ('tool', 'Tool'),
    ]

    id = models.CharField(max_length=100, primary_key=True)
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=MODULE_TYPES)
    html_file = models.CharField(max_length=200)
    difficulty = models.IntegerField(default=1)
    description = models.TextField(blank=True, null=True)
    role_title = models.CharField(max_length=200, blank=True, null=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return self.title


class Milestone(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='milestones')
    milestone_key = models.CharField(max_length=50)
    label = models.CharField(max_length=500)
    weight = models.IntegerField(default=10)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'{self.module_id} — {self.label}'


class EfficiencyThreshold(models.Model):
    module = models.OneToOneField(Module, on_delete=models.CASCADE, primary_key=True, related_name='efficiency_thresholds')
    exceptional = models.IntegerField()
    proficient = models.IntegerField()
    satisfactory = models.IntegerField()
    poor = models.IntegerField()

    def __str__(self):
        return f'Thresholds for {self.module_id}'


class BonusCategory(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='bonus_criteria')
    bonus_key = models.CharField(max_length=100)
    label = models.CharField(max_length=300)
    points = models.IntegerField(default=5)

    def __str__(self):
        return f'{self.module_id}: {self.label}'


class SupervisorTip(models.Model):
    VARIANTS = [
        ('default', 'Default'),
        ('warn', 'Warning'),
        ('danger', 'Danger'),
        ('good', 'Good'),
        ('purple', 'Purple'),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='tips')
    sort_order = models.IntegerField(default=0)
    icon = models.CharField(max_length=10, default='💡')
    variant = models.CharField(max_length=20, choices=VARIANTS, default='default')
    tip_text = models.TextField()

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'{self.module_id} tip #{self.sort_order}'


class GradeDescriptor(models.Model):
    grade = models.CharField(max_length=2, primary_key=True)
    min_score = models.IntegerField()
    label = models.CharField(max_length=100)
    description = models.TextField()

    class Meta:
        ordering = ['-min_score']

    def __str__(self):
        return f'Grade {self.grade}: {self.label}'


class AssessmentResult(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assessment_results',
    )
    level_key = models.CharField(max_length=100)
    score = models.IntegerField()
    grade = models.CharField(max_length=2)
    tier_label = models.CharField(max_length=100)
    milestones_done = models.IntegerField()
    milestones_total = models.IntegerField()
    efficiency_label = models.CharField(max_length=100)
    bonus_earned = models.IntegerField(default=0)
    note = models.TextField(default='', blank=True)
    token_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.level_key} — {self.grade} ({self.score}/100)'
