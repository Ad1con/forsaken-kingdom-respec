"""Hero definitions: campaign part, base abilities, talent rows and names.

Names come from the ability records inside the saves themselves, so they match
what the game displays. Every hero has four ability slots (Q W E R). A talent
row may modify one slot, in which case picking it swaps that slot's ability for
a talented variant (choice a/b/c -> variant 1/2/3); the variant id prefix is
per hero and per slot (`AHhs` -> `AHv1`, `AUwf` -> `AUw1`). Rows with no slot
are passives: the talent object alone.

Each choice carries its own talent id, because a row is not always the ids
sharing a row digit. Act One Garek is the exception that proves it: the game
groups his passive talents as UT5a/UT5b/UT6a and UT5c/UT6b/UT6c. The row keys
run in the order the Talents screen shows them, which for the Act One heroes
puts a passive row third rather than last.

Heroes are keyed by unit type id. `order` is the left-to-right order they are
shown in. `max_levels` is only a fallback: every save
carries the real caps, and the hero level each ability needs for its first
point, in a block next to the ability list, and those win when present.

`level_skip` is how much more hero level each rank after the first costs, so
rank N needs `level_required + (N - 1) * level_skip`. The save does not carry
it, so it is read off the game's learn tooltips; FORMAT.md has the readings.
"""

CHOICES = 'abc'

# The act heroes carry through unchanged, so one definition covers every act. A
# hero whose ability list is not in the save is simply not found.
ACTS = ('Act One', 'Act Two', 'Act Three')

# (part, map prefixes, confirmed against a real save). An act can introduce a
# hero the editor has never seen, so an unconfirmed part says so.
PARTS = [
    ('Prologue',  ('HumanRE',),   True),
    ('Act One',   ('UndeadRE01',), True),
    ('Act Two',   ('UndeadRE02',), True),
    ('Act Three', ('UndeadRE03',), False),
]
CHECKED = {name for name, _prefixes, ok in PARTS if ok}

# row: (label, [(choice name, talent id) x3], index of the ability it modifies or None)
HEROES = {
    # ---------------------------------------------------------------- Prologue
    'Hctr': dict(
        name='Garek', parts=('Prologue',), order=1,
        cache_key='Garek', talent_prefix='GT', max_levels=[3, 3, 3, 1],
        level_skip=[2, 2, 2, 6],
        base=['AHsw', 'AHbd', 'AHch', 'AHwc'],
        variant={'AHsw': 'AHs', 'AHbd': 'AHb', 'AHch': 'AHc', 'AHwc': None},
        abilities=['Sweeping Strike', 'Unyielding Guard', 'Valiant Charge', 'Warcry'],
        rows={
            1: ('Sweeping Strike', [('Crippling Blow', 'GT1a'), ('Rend Armor', 'GT1b'),
                                    ('Storm of Steel', 'GT1c')], 0),
            2: ('Unyielding Guard', [('Retaliation', 'GT2a'), ('Riposte', 'GT2b'),
                                     ('Blade Mastery', 'GT2c')], 1),
            3: ('Valiant Charge', [('Into the Fray!', 'GT3a'), ('Shoulder Bash', 'GT3b'),
                                   ('Stamina Training', 'GT3c')], 2),
            4: ('Warcry', [('Unbreakable', 'GT4a'), ('Combat Tempo', 'GT4b'),
                           ('Unstoppable Might', 'GT4c')], 3),
        }),
    'Hctl': dict(
        name='Landen', parts=('Prologue',), order=2,
        cache_key='Landen', talent_prefix='LT', max_levels=[3, 3, 3, 1],
        level_skip=[2, 2, 2, 6],
        base=['AHhs', 'AHen', 'AHic', 'AHct'],
        variant={'AHhs': 'AHv', 'AHen': 'AHe', 'AHic': 'AHi', 'AHct': None},
        abilities=['Heroic Slash', 'Apprehend', 'Inspire Courage', 'Raise the Banner'],
        rows={
            1: ('Heroic Slash', [("Valor's Reward", 'LT1a'), ('Judgement', 'LT1b'),
                                 ('Press the Attack', 'LT1c')], 0),
            2: ('Apprehend', [('Mass Arrest', 'LT2a'), ('Weighted Net', 'LT2b'),
                              ('Exposed Defenses', 'LT2c')], 1),
            3: ('Inspire Courage', [('Rally', 'LT3a'), ('Second Wind', 'LT3b'),
                                    ('Born Leader', 'LT3c')], 2),
            4: ('Raise the Banner', [('Perseverance', 'LT4a'), ('Against All Odds', 'LT4b'),
                                     ('Renewed Vigor', 'LT4c')], 3),
        }),
    'Hjsm': dict(
        name='Ilastar', parts=('Prologue',), order=3,
        cache_key='Ilastar', talent_prefix='IT', max_levels=[3, 3, 3, 1],
        level_skip=[2, 2, 2, 6],
        base=['AHas', 'AHsf', 'AHmc', 'AHsl'],
        variant={'AHas': 'AHa', 'AHsf': 'AHm', 'AHmc': 'AHz', 'AHsl': 'AHl'},
        abilities=['Sacred Aura', "Light's Mercy", 'Mind Control', 'Holy Bolts'],
        rows={
            1: ("Light's Mercy", [('Purifying Flame', 'IT1a'), ('Holy Nova', 'IT1b'),
                                  ('Radiant Embrace', 'IT1c')], 1),
            2: ('Mind Control', [('Unwilling Bomb', 'IT2a'), ('Mindbreaker', 'IT2b'),
                                 ('Voice of Authority', 'IT2c')], 2),
            3: ('Sacred Aura', [('Sacred Rebuke', 'IT3a'), ('Clarity of Mind', 'IT3b'),
                                ('Spiritual Renewal', 'IT3c')], 0),
            4: ('Holy Bolts', [('Divine Reservoir', 'IT4a'), ("Light's Grace", 'IT4b'),
                               ('Holy Light', 'IT4c')], 3),
        }),
    # ---------------------------------------------------------------- Act One
    'Uany': dict(
        name='Anya', parts=ACTS, order=1, cache_key='TransitionAnya', talent_prefix='AT',
        max_levels=[5, 5, 5, 3], level_skip=[4, 4, 4, 6],
        base=['AUwf', 'AUla', 'AUdb', 'AUwc'],
        variant={'AUwf': 'AUw', 'AUla': 'AUl', 'AUdb': 'AUd', 'AUwc': 'AUi'},
        abilities=['Withering Fire', 'Soul Lantern', 'Deathseeker Arrows', "Banshee's Wail"],
        rows={
            1: ('Withering Fire', [('Rain of Arrows', 'AT1a'), ('Deathmark', 'AT1b'),
                                   ('Deadeye', 'AT1c')], 0),
            2: ('Soul Lantern', [('Spirit Leech', 'AT2a'), ('Wraithguard', 'AT2b'),
                                 ('Guiding Light', 'AT2c')], 1),
            3: ('Attacks', [('Marksmanship', 'AT5a'), ('Arcane Archer', 'AT5b'),
                            ('Poison-tipped Arrows', 'AT5c')], None),
            4: ('Deathseeker Arrows', [('Death Sentence', 'AT3a'), ('Flow State', 'AT3b'),
                                       ('Umbral Rupture', 'AT3c')], 2),
            5: ("Banshee's Wail", [('Soul Harvest', 'AT4a'), ('Curse of the Darkfallen', 'AT4b'),
                                   ('Howling Tempest', 'AT4c')], 3),
            6: ('Stats', [("Ranger's Dexterity", 'AT6a'), ('Heightened Reflexes', 'AT6b'),
                          ('Blackened Soul', 'AT6c')], None),
        }),
    'Hleo': dict(
        name='Leonid', parts=ACTS, order=3, cache_key='TransitionLeonid', talent_prefix='BT',
        max_levels=[5, 5, 5, 3], level_skip=[4, 4, 4, 6],
        base=['AHhr', 'AHhc', 'AHgr', 'AHgh'],
        # The one hero whose prefixes are not his base ids' first three
        # characters: two pairs of his would collide (FORMAT.md).
        variant={'AHhr': 'AHh', 'AHhc': 'AHu', 'AHgr': 'AHg', 'AHgh': 'AHq'},
        abilities=['Headsplitter', 'Provoke', 'Grit', 'Guiding Hand'],
        rows={
            1: ('Headsplitter', [('Battle Fury', 'BT1a'), ('Staggering Impact', 'BT1b'),
                                 ('Meteor Strike', 'BT1c')], 0),
            2: ('Provoke', [('Reckless Abandon', 'BT2a'), ('Eye for Eye', 'BT2b'),
                            ('Indomitable', 'BT2c')], 1),
            3: ('Grit', [('Retribution', 'BT3a'), ('Unbreakable Spirit', 'BT3b'),
                         ('Tenacity', 'BT3c')], 2),
            4: ('Guiding Hand', [('Last Stand', 'BT4a'), ('Martial Mastery', 'BT4b'),
                                 ('Hand of Justice', 'BT4c')], 3),
            5: ('Defense', [('Iron Will', 'BT5a'), ("Veteran's Resilience", 'BT5b'),
                            ('Undead Vitality', 'BT5c')], None),
            6: ('Stats', [('Juggernaut', 'BT6a'), ('Thick Skin', 'BT6b'),
                          ('Discipline', 'BT6c')], None),
        }),
    'Ugrk': dict(
        name='Garek', parts=ACTS, order=2, cache_key='TransitionGarek', talent_prefix='UT',
        max_levels=[5, 5, 5, 3], level_skip=[4, 4, 4, 6],
        base=['AUsw', 'AUbd', 'AUbr', 'AUvg'],
        variant={'AUsw': 'AUs', 'AUbd': 'AUb', 'AUbr': 'AUr', 'AUvg': 'AUv'},
        abilities=['Relentless Cleave', 'Undying Defiance', 'Battering Ram', 'Grim Conviction'],
        rows={
            1: ('Relentless Cleave', [('Forsaken Might', 'UT1a'), ('Bloodthirst', 'UT1b'),
                                      ('Bladestorm', 'UT1c')], 0),
            2: ('Undying Defiance', [('Counter Attack', 'UT2a'), ('Parry', 'UT2b'),
                                     ('The Best Defense...', 'UT2c')], 1),
            3: ('Combat', [('Improved Armor', 'UT5a'), ('Swordsmanship', 'UT5b'),
                           ('Mighty Swing', 'UT6a')], None),
            4: ('Battering Ram', [('Endurance', 'UT3a'), ('Thirst For Battle', 'UT3b'),
                                  ('Furious Charge', 'UT3c')], 2),
            5: ('Grim Conviction', [('Inner Fire', 'UT4a'), ('Soulthirst', 'UT4b'),
                                    ('Unending Fury', 'UT4c')], 3),
            6: ('Stats', [('All Brawn', 'UT5c'), ('Quick Recovery', 'UT6b'),
                          ("Warrior's Focus", 'UT6c')], None),
        }),
}


def part_of_map(map_name):
    for part, prefixes, _checked in PARTS:
        if map_name.startswith(prefixes):
            return part
    return None


def choices(utype, row):
    """[(display name, talent id)] for a row, in a/b/c order."""
    return HEROES[utype]['rows'][row][1]


def talent_names(utype, row):
    return [name for name, _rid in choices(utype, row)]


def talent_id(utype, row, choice):
    return choices(utype, row)[CHOICES.index(choice)][1]


def talent_name(utype, row, choice):
    return choices(utype, row)[CHOICES.index(choice)][0]
