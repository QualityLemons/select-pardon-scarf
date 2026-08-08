from django import forms


LEVEL_CHOICES = [
    ('', '— Select a level —'),
    ('level1',        'Level 1 — Start/Stop Latching Circuit (Conveyor Belt)'),
    ('level2',        'Level 2 — Tank Filling System (Process Control)'),
    ('level3',        'Level 3 — Modbus TCP Communication'),
    ('level4',        'Level 4 — Safety Interlock (Drill / Guard Gate)'),
    ('level5',        'Level 5 — Timed Conveyor (TON Instruction)'),
    ('level6',        'Level 6 — Sequential Batching (State Machine)'),
    ('multimeter',    'Tool — Digital Multimeter Simulator'),
    ('plc-primer',    'Foundations — PLC Boot Camp / Glossary'),
    ('learn-your-log','Lesson — Maintenance Logging'),
]

SKILL_CHOICES = [
    ('', '— Select a skill area —'),
    ('ladder_logic',   'Ladder Logic & Circuit Behaviour'),
    ('fault_finding',  'Fault Finding & Diagnosis'),
    ('safety',         'Safety Systems & Interlocks'),
    ('timers_counters','Timers & Counters'),
    ('comms',          'Industrial Communications (Modbus TCP)'),
    ('documentation',  'Maintenance Documentation'),
    ('general',        'General Understanding'),
]

RATING_CHOICES = [
    (1, '1 — I need more practice'),
    (2, '2 — I partially understood it'),
    (3, '3 — I understood the basics'),
    (4, '4 — I understood it well'),
    (5, '5 — I could explain this to someone else'),
]


class ReflectionForm(forms.Form):
    """
    Learner reflection / mission-log entry form.
    Creates a MissionLogEntry record on valid submission.
    """

    level = forms.ChoiceField(
        label='Which level or module is this about?',
        choices=LEVEL_CHOICES,
        error_messages={'required': 'Please choose a level or module.'},
    )

    skill = forms.ChoiceField(
        label='Which skill area are you reflecting on?',
        choices=SKILL_CHOICES,
        error_messages={'required': 'Please choose a skill area.'},
    )

    notes = forms.CharField(
        label='Your reflection',
        widget=forms.Textarea(attrs={
            'rows': 6,
            'placeholder': (
                'Describe what you did, what you observed, and what you learned. '
                'For example: what happened when you pressed START? '
                'What surprised you? What would you do differently next time?'
            ),
        }),
        min_length=30,
        max_length=1000,
        error_messages={
            'required':  'Please write a reflection before submitting.',
            'min_length': 'Your reflection must be at least 30 characters. '
                          'Try describing what you observed or learned in more detail.',
            'max_length': 'Your reflection must be 1000 characters or fewer.',
        },
    )

    rating = forms.ChoiceField(
        label='How confident do you feel about this skill now?',
        choices=RATING_CHOICES,
        widget=forms.RadioSelect,
        error_messages={'required': 'Please choose a confidence rating.'},
    )

    # ------------------------------------------------------------------ #
    # Field-level validation                                               #
    # ------------------------------------------------------------------ #

    def clean_level(self):
        value = self.cleaned_data.get('level', '')
        if not value:
            raise forms.ValidationError('Please choose a level or module.')
        return value

    def clean_skill(self):
        value = self.cleaned_data.get('skill', '')
        if not value:
            raise forms.ValidationError('Please choose a skill area.')
        return value

    def clean_rating(self):
        value = self.cleaned_data.get('rating')
        try:
            rating = int(value)
        except (TypeError, ValueError):
            raise forms.ValidationError('Please choose a confidence rating.')
        if rating not in range(1, 6):
            raise forms.ValidationError('Rating must be between 1 and 5.')
        return rating
