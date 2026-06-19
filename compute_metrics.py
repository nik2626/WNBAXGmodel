import json
import math
from collections import defaultdict

# ── SHOT ARCHETYPE CLASSIFICATION ────────────────────────────────────────────
# This is the core of SQE. Every shot gets assigned to one of these buckets.
# Each bucket gets a league historical FG% which becomes the SQE baseline.

def classify_zone(zone_basic, zone_area):
    """Map WNBA API zone strings to our simplified zones."""
    z = zone_basic or ''
    a = zone_area or ''
    if z == 'Restricted Area':
        return 'RA'
    elif z == 'In The Paint (Non-RA)':
        return 'PAINT'
    elif z == 'Mid-Range':
        if 'Left' in a:
            return 'MID_L'
        elif 'Right' in a:
            return 'MID_R'
        else:
            return 'MID_C'
    elif z == 'Left Corner 3':
        return 'LC3'
    elif z == 'Right Corner 3':
        return 'RC3'
    elif z == 'Above the Break 3':
        if 'Left' in a:
            return 'ATB3_L'
        elif 'Right' in a:
            return 'ATB3_R'
        else:
            return 'ATB3_C'
    elif z == 'Backcourt':
        return 'BACK'
    return 'OTHER'

def classify_shot_type(action_type):
    """Classify shot action into broad type families."""
    a = (action_type or '').lower()
    if any(x in a for x in ['layup', 'dunk', 'tip', 'alley', 'putback', 'cutting', 'finger roll']):
        return 'AT_RIM'
    elif any(x in a for x in ['hook', 'floater', 'floating']):
        return 'FLOATER'
    elif any(x in a for x in ['pullup', 'pull-up', 'step back', 'turnaround', 'fadeaway']):
        return 'SELF_CREATE'
    elif 'catch and shoot' in a:
        return 'CATCH_SHOOT'
    elif 'jump shot' in a or 'bank' in a:
        return 'JUMP'
    return 'OTHER'

def classify_clock(period, minutes_remaining, seconds_remaining):
    """
    Classify shot clock bucket.
    We approximate shot clock from period time remaining.
    Late period (under 4 min) + late shot = likely late clock.
    """
    try:
        total_seconds = int(minutes_remaining) * 60 + int(seconds_remaining)
    except:
        return 'MID'
    # Rough shot clock approximation
    if total_seconds <= 4:
        return 'LATE'   # 0-4 seconds left, likely late clock
    elif total_seconds <= 14:
        return 'MID'    # mid clock
    else:
        return 'EARLY'  # early clock, good look

def is_transition(action_type, shot_type_class):
    """Approximate transition from action type."""
    a = (action_type or '').lower()
    return 'running' in a or 'fast break' in a

def is_garbage_time(period, score_margin=None):
    """Flag OT periods as potential garbage time."""
    return period >= 5

def build_archetype_key(zone, shot_type, clock, transition):
    """
    Combine features into one archetype string.
    Example: RA_AT_RIM_EARLY_HALF
    """
    trans = 'TRANS' if transition else 'HALF'
    return f'{zone}_{shot_type}_{clock}_{trans}'

def get_point_value(zone):
    """Return point value for shot zone."""
    if zone in ['LC3', 'RC3', 'ATB3_L', 'ATB3_R', 'ATB3_C', 'BACK']:
        return 3
    return 2

# ── CONTEST PROXY (Version 1 — no defender distance data) ────────────────────
# Until we have real contest data, we proxy contest level from:
# assisted/unassisted, shot type, clock bucket
# This is weaker than real contest data but better than ignoring it entirely

def proxy_contest(shot_type, assisted, clock, zone):
    """
    Returns estimated contest bucket:
    WO = Wide Open, OP = Open, TI = Tight, SM = Smothered
    """
    # Catch and shoot = likely more open (came off screen/pass)
    if shot_type == 'CATCH_SHOOT':
        if assisted:
            return 'OP'   # assisted catch and shoot = probably open
        return 'TI'

    # At rim — highly contested by nature unless transition
    if shot_type == 'AT_RIM':
        if clock == 'EARLY':
            return 'OP'   # transition/early = more open
        return 'TI'

    # Self created late clock = likely contested
    if shot_type == 'SELF_CREATE':
        if clock == 'LATE':
            return 'SM'
        return 'TI'

    # Corner 3s that are assisted = usually wide open
    if zone in ['LC3', 'RC3'] and assisted:
        return 'WO'

    # Default
    if clock == 'LATE':
        return 'TI'
    if assisted:
        return 'OP'
    return 'TI'

# ── HISTORICAL LEAGUE BASELINES ───────────────────────────────────────────────
# For each archetype, compute weighted historical FG%:
# 50% current season + 30% last 5 years + 20% beyond that

def build_baselines(current_shots, historical_shots_by_season):
    """
    Build league average FG% for each archetype.
    Returns dict: archetype_key -> {fga, fgm, fg_pct, point_value}
    """
    print('Building league baselines...')

    # Group shots by season and archetype
    archetype_data = defaultdict(lambda: defaultdict(lambda: {'fga': 0, 'fgm': 0}))

    def process_season(shots, season_label):
        for shot in shots:
            zone = classify_zone(
                shot.get('SHOT_ZONE_BASIC', ''),
                shot.get('SHOT_ZONE_AREA', '')
            )
            shot_type = classify_shot_type(shot.get('ACTION_TYPE', ''))
            clock = classify_clock(
                shot.get('PERIOD', 1),
                shot.get('MINUTES_REMAINING', 12),
                shot.get('SECONDS_REMAINING', 0)
            )
            transition = is_transition(shot.get('ACTION_TYPE', ''), shot_type)
            archetype = build_archetype_key(zone, shot_type, clock, transition)
            made = int(shot.get('SHOT_MADE_FLAG', 0))
            archetype_data[season_label][archetype]['fga'] += 1
            archetype_data[season_label][archetype]['fgm'] += made

    # Process current season
    process_season(current_shots, 'current')

    # Process historical seasons
    all_seasons = list(historical_shots_by_season.keys())
    all_seasons.sort()
    recent_5 = all_seasons[-5:] if len(all_seasons) >= 5 else all_seasons
    older = [s for s in all_seasons if s not in recent_5]

    for season in recent_5:
        process_season(historical_shots_by_season[season], f'recent_{season}')
    for season in older:
        process_season(historical_shots_by_season[season], f'older_{season}')

    # Get all archetypes
    all_archetypes = set()
    for season_data in archetype_data.values():
        all_archetypes.update(season_data.keys())

    baselines = {}
    for archetype in all_archetypes:
        # Aggregate by era
        curr = archetype_data['current'][archetype]
        curr_fg = curr['fgm'] / curr['fga'] if curr['fga'] > 0 else None

        recent_fga = sum(archetype_data[k][archetype]['fga'] for k in archetype_data if k.startswith('recent_'))
        recent_fgm = sum(archetype_data[k][archetype]['fgm'] for k in archetype_data if k.startswith('recent_'))
        recent_fg = recent_fgm / recent_fga if recent_fga > 0 else None

        older_fga = sum(archetype_data[k][archetype]['fga'] for k in archetype_data if k.startswith('older_'))
        older_fgm = sum(archetype_data[k][archetype]['fgm'] for k in archetype_data if k.startswith('older_'))
        older_fg = older_fgm / older_fga if older_fga > 0 else None

        # Weighted blend: 50% current, 30% last 5 years, 20% older
        # Fall back if data missing
        weights = []
        values = []
        if curr_fg is not None:
            weights.append(0.50)
            values.append(curr_fg)
        if recent_fg is not None:
            weights.append(0.30)
            values.append(recent_fg)
        if older_fg is not None:
            weights.append(0.20)
            values.append(older_fg)

        if not values:
            continue

        # Normalize weights
        total_w = sum(weights)
        fg_pct = sum(v * (w / total_w) for v, w in zip(values, weights))

        # Get point value from zone part of archetype key
        zone_part = archetype.split('_')[0]
        pts = 3 if zone_part in ['LC3', 'RC3', 'ATB3', 'BACK'] else 2

        baselines[archetype] = {
            'fg_pct': round(fg_pct, 4),
            'point_value': pts,
            'sqe_per_shot': round(fg_pct * pts * 100, 2),  # per 100
            'total_fga': (curr['fga'] + recent_fga + older_fga),
        }

    print(f'Built {len(baselines)} shot archetypes')
    return baselines

# ── SHOOTER BASELINES FOR SAXE ────────────────────────────────────────────────
# For each player × archetype, compute their skill baseline
# Bayesian shrinkage: blend toward league avg when sample is small

def build_shooter_baselines(current_shots, historical_shots_by_season, league_baselines):
    """
    For each player, compute their FG% per archetype across seasons.
    Returns: player_id -> archetype -> {fg_pct, fga, saxe_per_shot}
    """
    print('Building shooter baselines...')

    # Accumulate per player per archetype
    player_arch = defaultdict(lambda: defaultdict(lambda: {
        'curr_fga': 0, 'curr_fgm': 0,
        'hist_fga': 0, 'hist_fgm': 0,
        'name': ''
    }))

    def process(shots, is_current):
        for shot in shots:
            pid = str(shot.get('PLAYER_ID', ''))
            pname = shot.get('PLAYER_NAME', '')
            if not pid:
                continue
            zone = classify_zone(
                shot.get('SHOT_ZONE_BASIC', ''),
                shot.get('SHOT_ZONE_AREA', '')
            )
            shot_type = classify_shot_type(shot.get('ACTION_TYPE', ''))
            clock = classify_clock(
                shot.get('PERIOD', 1),
                shot.get('MINUTES_REMAINING', 12),
                shot.get('SECONDS_REMAINING', 0)
            )
            transition = is_transition(shot.get('ACTION_TYPE', ''), shot_type)
            archetype = build_archetype_key(zone, shot_type, clock, transition)
            made = int(shot.get('SHOT_MADE_FLAG', 0))

            player_arch[pid][archetype]['name'] = pname
            if is_current:
                player_arch[pid][archetype]['curr_fga'] += 1
                player_arch[pid][archetype]['curr_fgm'] += made
            else:
                player_arch[pid][archetype]['hist_fga'] += 1
                player_arch[pid][archetype]['hist_fgm'] += made

    process(current_shots, True)
    for shots in historical_shots_by_season.values():
        process(shots, False)

    # Build shooter skill per archetype with shrinkage
    shooter_baselines = {}
    MIN_SAMPLE = 30  # below this, shrink heavily toward league avg

    for pid, archetypes in player_arch.items():
        shooter_baselines[pid] = {}
        player_name = ''

        for arch, d in archetypes.items():
            player_name = d['name'] or player_name
            league = league_baselines.get(arch, {})
            league_fg = league.get('fg_pct', 0.40)
            pts = league.get('point_value', 2)

            curr_fga = d['curr_fga']
            curr_fgm = d['curr_fgm']
            hist_fga = d['hist_fga']
            hist_fgm = d['hist_fgm']

            curr_fg = curr_fgm / curr_fga if curr_fga > 0 else None
            hist_fg = (curr_fgm + hist_fgm) / (curr_fga + hist_fga) if (curr_fga + hist_fga) > 0 else None

            total_fga = curr_fga + hist_fga

            # Shrinkage weights — more league avg when small sample
            if total_fga >= MIN_SAMPLE:
                w_curr = 0.50
                w_hist = 0.30
                w_league = 0.20
            elif total_fga >= 15:
                w_curr = 0.35
                w_hist = 0.25
                w_league = 0.40
            else:
                w_curr = 0.20
                w_hist = 0.10
                w_league = 0.70

            # Build blended estimate
            values, weights = [], []
            if curr_fg is not None:
                values.append(curr_fg)
                weights.append(w_curr)
            if hist_fg is not None:
                values.append(hist_fg)
                weights.append(w_hist)
            values.append(league_fg)
            weights.append(w_league)

            total_w = sum(weights)
            skill_fg = sum(v * (w / total_w) for v, w in zip(values, weights))

            shooter_baselines[pid][arch] = {
                'fg_pct': round(skill_fg, 4),
                'saxe_per_shot': round(skill_fg * pts * 100, 2),
                'fga': total_fga,
                'raw_fg': round(curr_fg, 4) if curr_fg is not None else None,
            }

        shooter_baselines[pid]['_name'] = player_name

    print(f'Built shooter baselines for {len(shooter_baselines)} players')
    return shooter_baselines

# ── PER-SHOT SQE AND SAXE ─────────────────────────────────────────────────────

def compute_shot_metrics(shots, league_baselines, shooter_baselines):
    """
    For every shot this season, compute:
    - archetype
    - SQE value (league baseline for that archetype)
    - SAXE value (shooter-adjusted baseline)
    - contest proxy
    Returns enriched shot list
    """
    print('Computing per-shot SQE and SAXE...')
    enriched = []

    for shot in shots:
        pid = str(shot.get('PLAYER_ID', ''))
        zone = classify_zone(
            shot.get('SHOT_ZONE_BASIC', ''),
            shot.get('SHOT_ZONE_AREA', '')
        )
        shot_type = classify_shot_type(shot.get('ACTION_TYPE', ''))
        clock = classify_clock(
            shot.get('PERIOD', 1),
            shot.get('MINUTES_REMAINING', 12),
            shot.get('SECONDS_REMAINING', 0)
        )
        transition = is_transition(shot.get('ACTION_TYPE', ''), shot_type)
        archetype = build_archetype_key(zone, shot_type, clock, transition)
        pts = get_point_value(zone)
        made = int(shot.get('SHOT_MADE_FLAG', 0))
        gt = is_garbage_time(shot.get('PERIOD', 1))

        # Contest proxy
        assisted = shot_type == 'CATCH_SHOOT'
        contest = proxy_contest(shot_type, assisted, clock, zone)

        # SQE — league baseline
        baseline = league_baselines.get(archetype, {})
        league_fg = baseline.get('fg_pct', 0.40)
        sqe = round(league_fg * pts * 100, 3)

        # SAXE — shooter adjusted
        player_archs = shooter_baselines.get(pid, {})
        player_arch_data = player_archs.get(archetype, {})
        player_fg = player_arch_data.get('fg_pct', league_fg)
        saxe = round(player_fg * pts * 100, 3)

        enriched.append({
            'game_id': shot.get('GAME_ID'),
            'player_id': pid,
            'player_name': shot.get('PLAYER_NAME'),
            'team_id': str(shot.get('TEAM_ID')),
            'team_name': shot.get('TEAM_NAME'),
            'period': shot.get('PERIOD'),
            'zone': zone,
            'shot_type': shot_type,
            'clock_bucket': clock,
            'transition': transition,
            'archetype': archetype,
            'contest_proxy': contest,
            'point_value': pts,
            'made': made,
            'actual_pts': made * pts,
            'sqe': sqe,
            'saxe': saxe,
            'saxe_minus_sqe': round(saxe - sqe, 3),
            'garbage_time': gt,
            'loc_x': shot.get('LOC_X'),
            'loc_y': shot.get('LOC_Y'),
        })

    print(f'Computed metrics for {len(enriched)} shots')
    return enriched

# ── TEAM AGGREGATION ──────────────────────────────────────────────────────────

def aggregate_teams(enriched_shots, adv_stats, onoff_data):
    """Aggregate shot metrics to team level."""
    print('Aggregating team metrics...')

    teams = defaultdict(lambda: {
        'sqe_sum': 0, 'saxe_sum': 0, 'shot_count': 0,
        'actual_pts': 0, 'made': 0,
        'sqe_sum_gt': 0, 'saxe_sum_gt': 0, 'shot_count_gt': 0,
        'zone_counts': defaultdict(int),
        'zone_makes': defaultdict(int),
        'archetype_counts': defaultdict(int),
    })

    for shot in enriched_shots:
        tid = shot['team_id']
        t = teams[tid]
        t['team_name'] = shot['team_name']
        t['team_id'] = tid

        if not shot['garbage_time']:
            t['sqe_sum'] += shot['sqe']
            t['saxe_sum'] += shot['saxe']
            t['shot_count'] += 1
            t['actual_pts'] += shot['actual_pts']
            t['made'] += shot['made']
        else:
            t['sqe_sum_gt'] += shot['sqe']
            t['saxe_sum_gt'] += shot['saxe']
            t['shot_count_gt'] += 1

        t['zone_counts'][shot['zone']] += 1
        if shot['made']:
            t['zone_makes'][shot['zone']] += 1
        t['archetype_counts'][shot['archetype']] += 1

    # Add advanced stats
    adv_by_team = {str(r.get('TEAM_ID')): r for r in adv_stats}

    result = {}
    all_sqe = [t['sqe_sum'] / t['shot_count'] * 100 if t['shot_count'] > 0 else 100
               for t in teams.values() if t['shot_count'] > 0]
    league_avg_sqe = sum(all_sqe) / len(all_sqe) if all_sqe else 100

    for tid, t in teams.items():
        n = t['shot_count']
        if n == 0:
            continue

        sqe_raw = t['sqe_sum'] / n
        saxe_raw = t['saxe_sum'] / n

        adv = adv_by_team.get(str(tid), {})

        result[tid] = {
            'team_id': tid,
            'team_name': t.get('team_name', ''),
            'shots': n,
            'sqe_raw': round(sqe_raw * 100, 2),
            'saxe_raw': round(saxe_raw * 100, 2),
            'actual_fg_pct': round(t['made'] / n, 4) if n > 0 else 0,
            'zone_pcts': {
                z: round(c / n, 4)
                for z, c in t['zone_counts'].items()
            },
            'zone_fg_pcts': {
                z: round(t['zone_makes'].get(z, 0) / c, 4)
                for z, c in t['zone_counts'].items() if c > 0
            },
            'off_rating': adv.get('OFF_RATING', 0),
            'pace': adv.get('PACE', 0),
            'tov_pct': adv.get('TM_TOV_PCT', 0),
            'ast_pct': adv.get('AST_PCT', 0),
        }

    # Normalize SQE and SAXE to league avg = 100
    sqe_vals = [t['sqe_raw'] for t in result.values()]
    saxe_vals = [t['saxe_raw'] for t in result.values()]
    sqe_mean = sum(sqe_vals) / len(sqe_vals) if sqe_vals else 100
    saxe_mean = sum(saxe_vals) / len(saxe_vals) if saxe_vals else 100

    for tid in result:
        result[tid]['sqe'] = round((result[tid]['sqe_raw'] / sqe_mean) * 100, 1)
        result[tid]['saxe'] = round((result[tid]['saxe_raw'] / saxe_mean) * 100, 1)
        result[tid]['fit_delta'] = round(result[tid]['saxe'] - result[tid]['sqe'], 1)

    print(f'Aggregated {len(result)} teams')
    return result

# ── PLAYER AGGREGATION ────────────────────────────────────────────────────────

def aggregate_players(enriched_shots, league_baselines):
    """Aggregate shot metrics to player level."""
    print('Aggregating player metrics...')

    players = defaultdict(lambda: {
        'sqe_sum': 0, 'saxe_sum': 0, 'shots': 0,
        'actual_pts': 0, 'made': 0,
        'zone_counts': defaultdict(int),
        'zone_makes': defaultdict(int),
    })

    for shot in enriched_shots:
        if shot['garbage_time']:
            continue
        pid = shot['player_id']
        p = players[pid]
        p['player_name'] = shot['player_name']
        p['player_id'] = pid
        p['team_id'] = shot['team_id']
        p['team_name'] = shot['team_name']
        p['sqe_sum'] += shot['sqe']
        p['saxe_sum'] += shot['saxe']
        p['shots'] += 1
        p['actual_pts'] += shot['actual_pts']
        p['made'] += shot['made']
        p['zone_counts'][shot['zone']] += 1
        if shot['made']:
            p['zone_makes'][shot['zone']] += 1

    result = {}
    for pid, p in players.items():
        n = p['shots']
        if n < 20:
            continue
        result[pid] = {
            'player_id': pid,
            'player_name': p.get('player_name', ''),
            'team_id': p.get('team_id', ''),
            'team_name': p.get('team_name', ''),
            'shots': n,
            'sqe_per_shot': round(p['sqe_sum'] / n, 2),
            'saxe_per_shot': round(p['saxe_sum'] / n, 2),
            'actual_pts_per_shot': round(p['actual_pts'] / n, 3),
            'fg_pct': round(p['made'] / n, 4),
            'fit_delta': round((p['saxe_sum'] - p['sqe_sum']) / n, 2),
            'actual_over_saxe': round((p['actual_pts'] / n) - (p['saxe_sum'] / n / 100), 3),
            'zone_pcts': {
                z: round(c / n, 4)
                for z, c in p['zone_counts'].items()
            },
        }

    print(f'Aggregated {len(result)} players')
    return result

# ── ON/OFF PROCESSING ─────────────────────────────────────────────────────────

def process_onoff(onoff_raw):
    """Process teamplayeronoffsummary into clean on/off rows."""
    print('Processing on/off data...')
    rows = []

    for tid, data in onoff_raw.items():
        on_rows = data.get('on', [])
        off_rows = data.get('off', [])

        off_by_pid = {str(r.get('PLAYER_ID')): r for r in off_rows}

        for on in on_rows:
            pid = str(on.get('PLAYER_ID', ''))
            off = off_by_pid.get(pid, {})

            min_on = float(on.get('MIN', 0) or 0)
            min_off = float(off.get('MIN', 0) or 0)
            if min_on < 10 or min_off < 10:
                continue

            ortg_on = float(on.get('OFF_RATING', 0) or 0)
            ortg_off = float(off.get('OFF_RATING', 0) or 0)
            efg_on = float(on.get('EFG_PCT', 0) or 0)
            efg_off = float(off.get('EFG_PCT', 0) or 0)
            pace_on = float(on.get('PACE', 0) or 0)

            rows.append({
                'player_id': pid,
                'player_name': on.get('PLAYER_NAME', ''),
                'team_id': tid,
                'ortg_on': round(ortg_on, 1),
                'ortg_off': round(ortg_off, 1),
                'ortg_impact': round(ortg_on - ortg_off, 1),
                'efg_on': round(efg_on, 4),
                'efg_off': round(efg_off, 4),
                'efg_impact': round(efg_on - efg_off, 4),
                'min_on': round(min_on, 1),
                'min_off': round(min_off, 1),
                'pace_on': round(pace_on, 1),
            })

    rows.sort(key=lambda x: x['ortg_impact'], reverse=True)
    print(f'Processed {len(rows)} player on/off rows')
    return rows

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print('Loading raw data...')
    with open('raw_data.json', 'r') as f:
        raw = json.load(f)

    current_season = raw['currentSeason']
    current_shots = raw['shots'].get(current_season, [])
    historical_shots = raw.get('historicalShots', {})
    adv_stats = raw['advancedStats'].get(current_season, [])
    onoff_raw = raw['onoff'].get(current_season, {})

    print(f'Current season shots: {len(current_shots)}')
    print(f'Historical seasons: {list(historical_shots.keys())}')

    # Step 1: Build league baselines from all historical data
    league_baselines = build_baselines(current_shots, historical_shots)

    # Step 2: Build shooter baselines
    shooter_baselines = build_shooter_baselines(
        current_shots, historical_shots, league_baselines
    )

    # Step 3: Compute per-shot SQE and SAXE
    enriched_shots = compute_shot_metrics(
        current_shots, league_baselines, shooter_baselines
    )

    # Step 4: Aggregate to team and player level
    team_metrics = aggregate_teams(enriched_shots, adv_stats, onoff_raw)
    player_metrics = aggregate_players(enriched_shots, league_baselines)
    onoff_metrics = process_onoff(onoff_raw)

    # Step 5: Output final data.json
    output = {
        'fetchedAt': raw['fetchedAt'],
        'season': current_season,
        'teams': team_metrics,
        'players': player_metrics,
        'onoff': onoff_metrics,
        'baselines': league_baselines,
        'totalShots': len(enriched_shots),
        'archetypeCount': len(league_baselines),
    }

    with open('data.json', 'w') as f:
        json.dump(output, f)

    print(f'\nDone.')
    print(f'Teams: {len(team_metrics)}')
    print(f'Players: {len(player_metrics)}')
    print(f'On/off rows: {len(onoff_metrics)}')
    print(f'Shot archetypes: {len(league_baselines)}')
    print(f'data.json saved.')

if __name__ == '__main__':
    main()
