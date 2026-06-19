import requests
import json
import time
import random
from datetime import datetime
 
# ── SESSION SETUP ─────────────────────────────────────────────────────────────
# Use a session with cookies — mimics a real browser visiting stats.wnba.com
# This is the key to bypassing the Akamai bot protection
 
def make_session():
    session = requests.Session()
    session.headers.update({
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Origin': 'https://stats.wnba.com',
        'Referer': 'https://stats.wnba.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'x-nba-stats-origin': 'stats',
        'x-nba-stats-token': 'true',
    })
    # Visit the main page first to establish cookies
    try:
        session.get('https://stats.wnba.com', timeout=15)
        time.sleep(2)
    except:
        pass
    return session
 
BASE = 'https://stats.wnba.com/stats'
CURRENT_SEASON = '2025-26'
LID = '10'
 
HISTORICAL_SEASONS = [
    '2016-17', '2017-18', '2018-19', '2019-20', '2020-21',
    '2021-22', '2022-23', '2023-24', '2024-25'
]
 
TEAM_IDS = [
    1611661321, 1611661319, 1611661329, 1611661325, 1611661317,
    1611661323, 1611661388, 1611661320, 1611661392, 1611661391,
    1611661328, 1611661330, 1611661384, 1611661322, 1611661324
]
 
def get(session, endpoint, params, retries=4):
    url = f'{BASE}/{endpoint}'
    for attempt in range(retries):
        try:
            # Random delay to avoid rate limiting
            time.sleep(random.uniform(1.5, 3.0))
            r = session.get(url, params=params, timeout=45)
            print(f'  {endpoint} status: {r.status_code}')
            if r.status_code == 200:
                data = r.json()
                if data.get('resultSets'):
                    return data
            elif r.status_code == 429:
                # Rate limited — wait longer
                wait = 30 * (attempt + 1)
                print(f'  Rate limited. Waiting {wait}s...')
                time.sleep(wait)
            else:
                print(f'  Got {r.status_code}, retrying...')
                time.sleep(5 * (attempt + 1))
        except Exception as e:
            print(f'  Attempt {attempt+1} failed: {e}')
            time.sleep(5 * (attempt + 1))
    print(f'  FAILED after {retries} attempts: {endpoint}')
    return None
 
def parse_result_set(data, index=0):
    if not data or not data.get('resultSets'):
        return []
    rs = data['resultSets'][index]
    headers = rs['headers']
    rows = rs['rowSet']
    return [dict(zip(headers, row)) for row in rows]
 
def fetch_shot_chart(session, season):
    print(f'Fetching shot chart for {season}...')
    data = get(session, 'shotchartdetail', {
        'LeagueID': LID, 'Season': season,
        'SeasonType': 'Regular Season',
        'TeamID': 0, 'PlayerID': 0,
        'ContextMeasure': 'FGA',
        'DateFrom': '', 'DateTo': '', 'GameID': '',
        'GameSegment': '', 'LastNGames': 0, 'Location': '',
        'Month': 0, 'OpponentTeamID': 0, 'Outcome': '',
        'Period': 0, 'PlayerPosition': '', 'RookieYear': '',
        'SeasonSegment': '', 'VsConference': '', 'VsDivision': ''
    })
    shots = parse_result_set(data, 0)
    print(f'  Got {len(shots)} shots')
    return shots
 
def fetch_advanced_stats(session, season):
    print(f'Fetching advanced stats for {season}...')
    data = get(session, 'leaguedashteamstats', {
        'LeagueID': LID, 'Season': season,
        'SeasonType': 'Regular Season',
        'PerMode': 'PerPossession', 'MeasureType': 'Advanced',
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
 
def fetch_player_stats(session, season):
    print(f'Fetching player stats for {season}...')
    data = get(session, 'leaguedashplayerstats', {
        'LeagueID': LID, 'Season': season,
        'SeasonType': 'Regular Season',
        'PerMode': 'PerGame', 'MeasureType': 'Base',
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
 
def fetch_onoff(session, season):
    print(f'Fetching on/off for {season}...')
    all_onoff = {}
    for tid in TEAM_IDS:
        data = get(session, 'teamplayeronoffsummary', {
            'LeagueID': LID, 'Season': season,
            'SeasonType': 'Regular Season',
            'TeamID': tid, 'MeasureType': 'Base',
            'PerMode': 'PerPossession',
            'PaceAdjust': 'N', 'PlusMinus': 'N', 'Rank': 'N',
            'DateFrom': '', 'DateTo': '', 'GameSegment': '',
            'LastNGames': 0, 'Location': '', 'Month': 0,
            'OpponentTeamID': 0, 'Period': 0,
            'SeasonSegment': '', 'VsConference': '', 'VsDivision': ''
        })
        if data and data.get('resultSets') and len(data['resultSets']) >= 3:
            all_onoff[str(tid)] = {
                'on': parse_result_set(data, 1),
                'off': parse_result_set(data, 2)
            }
    return all_onoff
 
def main():
    print('Creating session...')
    session = make_session()
 
    output = {
        'fetchedAt': datetime.utcnow().isoformat() + 'Z',
        'currentSeason': CURRENT_SEASON,
        'shots': {},
        'advancedStats': {},
        'playerStats': {},
        'onoff': {},
        'historicalShots': {},
    }
 
    # Current season
    print('\n=== CURRENT SEASON ===')
    output['shots'][CURRENT_SEASON] = fetch_shot_chart(session, CURRENT_SEASON)
    output['advancedStats'][CURRENT_SEASON] = fetch_advanced_stats(session, CURRENT_SEASON)
    output['playerStats'][CURRENT_SEASON] = fetch_player_stats(session, CURRENT_SEASON)
    output['onoff'][CURRENT_SEASON] = fetch_onoff(session, CURRENT_SEASON)
 
    # Historical seasons for baselines
    print('\n=== HISTORICAL SEASONS ===')
    for season in HISTORICAL_SEASONS:
        shots = fetch_shot_chart(session, season)
        if shots:
            output['historicalShots'][season] = shots
        # Refresh session every few seasons
        if HISTORICAL_SEASONS.index(season) % 3 == 2:
            print('Refreshing session...')
            session = make_session()
 
    with open('raw_data.json', 'w') as f:
        json.dump(output, f)
 
    current = len(output['shots'].get(CURRENT_SEASON, []))
    historical = sum(len(v) for v in output['historicalShots'].values())
    print(f'\nDone. Current: {current} shots. Historical: {historical} shots.')
 
if __name__ == '__main__':
    main()
