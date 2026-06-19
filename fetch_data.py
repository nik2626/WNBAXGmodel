import requests
import json
import time
from datetime import datetime

HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://stats.wnba.com',
    'Referer': 'https://stats.wnba.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true',
}

BASE = 'https://stats.wnba.com/stats'
CURRENT_SEASON = '2025-26'
LID = '10'

# Historical seasons for building league baselines
HISTORICAL_SEASONS = [
    '2016-17', '2017-18', '2018-19', '2019-20', '2020-21',
    '2021-22', '2022-23', '2023-24', '2024-25', '2025-26'
]

TEAM_IDS = [
    1611661321, 1611661319, 1611661329, 1611661325, 1611661317,
    1611661323, 1611661388, 1611661320, 1611661392, 1611661391,
    1611661328, 1611661330, 1611661384, 1611661322, 1611661324
]

def get(endpoint, params, retries=3):
    url = f'{BASE}/{endpoint}'
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if data.get('resultSets'):
                return data
        except Exception as e:
            print(f'Attempt {attempt+1} failed for {endpoint}: {e}')
            time.sleep(2 ** attempt)
    return None

def parse_result_set(data, index=0):
    if not data or not data.get('resultSets'):
        return []
    rs = data['resultSets'][index]
    headers = rs['headers']
    rows = rs['rowSet']
    return [dict(zip(headers, row)) for row in rows]

def fetch_shot_chart(season):
    print(f'Fetching shot chart for {season}...')
    data = get('shotchartdetail', {
        'LeagueID': LID,
        'Season': season,
        'SeasonType': 'Regular Season',
        'TeamID': 0,
        'PlayerID': 0,
        'ContextMeasure': 'FGA',
        'DateFrom': '', 'DateTo': '', 'GameID': '',
        'GameSegment': '', 'LastNGames': 0, 'Location': '',
        'Month': 0, 'OpponentTeamID': 0, 'Outcome': '',
        'Period': 0, 'PlayerPosition': '', 'RookieYear': '',
        'SeasonSegment': '', 'VsConference': '', 'VsDivision': ''
    })
    shots = parse_result_set(data, 0)
    print(f'  Got {len(shots)} shots for {season}')
    return shots

def fetch_advanced_stats(season):
    print(f'Fetching advanced stats for {season}...')
    data = get('leaguedashteamstats', {
        'LeagueID': LID,
        'Season': season,
        'SeasonType': 'Regular Season',
        'PerMode': 'PerPossession',
        'MeasureType': 'Advanced',
        'Conference': '', 'DateFrom': '', 'DateTo': '',
        'Division': '', 'GameScope': '', 'GameSegment': '',
        'Height': '', 'LastNGames': 0, 'Location': '',
        'Month': 0, 'OpponentTeamID': 0, 'PORound': 0,
        'PaceAdjust': 'N', 'Period': 0, 'PlayerExperience': '',
        'PlayerPosition': '', 'PlusMinus': 'N', 'Rank': 'N',
        'SeasonSegment': '', 'ShotClockRange': '', 'StarterBench': '',
        'TeamID': 0, 'TwoWay': 0, 'VsConference': '', 'VsDivision': ''
    })
    return parse_result_set(data, 0)

def fetch_player_stats(season):
    print(f'Fetching player stats for {season}...')
    data = get('leaguedashplayerstats', {
        'LeagueID': LID,
        'Season': season,
        'SeasonType': 'Regular Season',
        'PerMode': 'PerGame',
        'MeasureType': 'Base',
        'Conference': '', 'DateFrom': '', 'DateTo': '',
        'Division': '', 'GameScope': '', 'GameSegment': '',
        'Height': '', 'LastNGames': 0, 'Location': '',
        'Month': 0, 'OpponentTeamID': 0, 'PORound': 0,
        'PaceAdjust': 'N', 'Period': 0, 'PlayerExperience': '',
        'PlayerPosition': '', 'PlusMinus': 'N', 'Rank': 'N',
        'SeasonSegment': '', 'ShotClockRange': '', 'StarterBench': '',
        'TeamID': 0, 'TwoWay': 0, 'VsConference': '', 'VsDivision': ''
    })
    return parse_result_set(data, 0)

def fetch_onoff(season):
    print(f'Fetching on/off data for {season}...')
    all_onoff = {}
    for tid in TEAM_IDS:
        data = get('teamplayeronoffsummary', {
            'LeagueID': LID,
            'Season': season,
            'SeasonType': 'Regular Season',
            'TeamID': tid,
            'MeasureType': 'Base',
            'PerMode': 'PerPossession',
            'PaceAdjust': 'N', 'PlusMinus': 'N', 'Rank': 'N',
            'DateFrom': '', 'DateTo': '', 'GameSegment': '',
            'LastNGames': 0, 'Location': '', 'Month': 0,
            'OpponentTeamID': 0, 'Period': 0,
            'SeasonSegment': '', 'VsConference': '', 'VsDivision': ''
        })
        if data and data.get('resultSets') and len(data['resultSets']) >= 3:
            on_court = parse_result_set(data, 1)
            off_court = parse_result_set(data, 2)
            all_onoff[str(tid)] = {
                'on': on_court,
                'off': off_court
            }
        time.sleep(0.6)
    return all_onoff

def fetch_pbpstats_shots(season):
    """
    Fetch enhanced shot data from pbpstats including:
    - shot clock
    - transition flag
    - assisted flag
    - dribbles before shot
    - touch time
    These fields are used as contest proxies for SQE v1
    """
    print(f'Fetching pbpstats data for {season}...')
    try:
        from pbpstats.client import Client
        settings = {
            'Games': {'source': 'web', 'data_provider': 'stats_nba'},
            'Possessions': {'source': 'web', 'data_provider': 'stats_nba'},
        }
        client = Client(settings)
        # pbpstats uses league prefix in season for WNBA
        # Game IDs starting with 10 = WNBA
        # This fetches aggregated shooting stats with tracking context
        response = requests.get(
            f'https://api.pbpstats.com/get-totals/wnba',
            params={
                'Season': season,
                'SeasonType': 'Regular Season',
                'EntityType': 'Player',
                'type': 'shooting'
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f'pbpstats fetch failed: {e} — will use proxy contest model')
    return None

def main():
    output = {
        'fetchedAt': datetime.utcnow().isoformat() + 'Z',
        'currentSeason': CURRENT_SEASON,
        'shots': {},
        'advancedStats': {},
        'playerStats': {},
        'onoff': {},
        'historicalShots': {},
        'pbpStats': {}
    }

    # Current season — full detail
    print('\n=== CURRENT SEASON ===')
    output['shots'][CURRENT_SEASON] = fetch_shot_chart(CURRENT_SEASON)
    time.sleep(1)
    output['advancedStats'][CURRENT_SEASON] = fetch_advanced_stats(CURRENT_SEASON)
    time.sleep(1)
    output['playerStats'][CURRENT_SEASON] = fetch_player_stats(CURRENT_SEASON)
    time.sleep(1)
    output['onoff'][CURRENT_SEASON] = fetch_onoff(CURRENT_SEASON)
    time.sleep(1)

    # Try pbpstats for enhanced shot context
    pbp = fetch_pbpstats_shots(CURRENT_SEASON)
    if pbp:
        output['pbpStats'][CURRENT_SEASON] = pbp

    # Historical seasons — shots only, for building league baselines
    print('\n=== HISTORICAL SEASONS (for baselines) ===')
    for season in HISTORICAL_SEASONS:
        if season == CURRENT_SEASON:
            continue
        shots = fetch_shot_chart(season)
        if shots:
            output['historicalShots'][season] = shots
        time.sleep(2)

    # Save raw data
    with open('raw_data.json', 'w') as f:
        json.dump(output, f)

    total_shots = len(output['shots'].get(CURRENT_SEASON, []))
    total_historical = sum(len(v) for v in output['historicalShots'].values())
    print(f'\nDone.')
    print(f'Current season shots: {total_shots}')
    print(f'Historical shots: {total_historical}')
    print(f'Raw data saved to raw_data.json')

if __name__ == '__main__':
    main()
