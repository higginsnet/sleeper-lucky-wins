import requests

BASE = "https://api.sleeper.app/v1"


def get_league(league_id):
    return requests.get(f"{BASE}/league/{league_id}").json()


def get_users(league_id):
    return requests.get(f"{BASE}/league/{league_id}/users").json()


def get_rosters(league_id):
    return requests.get(f"{BASE}/league/{league_id}/rosters").json()


def get_matchups(league_id, week):
    return requests.get(f"{BASE}/league/{league_id}/matchups/{week}").json()


def get_nfl_state():
    return requests.get(f"{BASE}/state/nfl").json()
