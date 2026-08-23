from django.contrib.auth.models import User
from django.db import models


class AssessmentResult(models.Model):
    """A saved Manager's Review attempt, linked to a registered user when logged in."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assessment_results",
        null=True,
        blank=True,
    )
    level_key = models.CharField(max_length=50)
    score = models.IntegerField()
    grade = models.CharField(max_length=2)
    tier_label = models.CharField(max_length=50)
    milestones_done = models.IntegerField()
    milestones_total = models.IntegerField()
    efficiency_label = models.CharField(max_length=50)
    bonus_earned = models.IntegerField(default=0)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.level_key} — {self.score}/100 ({self.grade})"

    def to_dict(self):
        return {
            "id": self.id,
            "level_key": self.level_key,
            "score": self.score,
            "grade": self.grade,
            "tier_label": self.tier_label,
            "milestones_done": self.milestones_done,
            "milestones_total": self.milestones_total,
            "efficiency_label": self.efficiency_label,
            "bonus_earned": self.bonus_earned,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }
