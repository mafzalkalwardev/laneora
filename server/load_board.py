"""Search the freight board with the session Laneora already holds.

Callers send a Laneora username. This module reads that account's stored
board token (the same localStorage login the desktop window injects) and asks
the board for loads. It does not create accounts and it does not return the
token or the cookie jar.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from app import USER_AGENT
from server.soft_admin_lib import load_config, load_local_users

BOARD_GRAPHQL = "https://freight.api.dat.com/one-web-bff/graphql"

_SEARCH = """
mutation CreateAndExecuteSearchMutation($createAndExecuteSearchCriteria: CreateAndExecuteSearchCriteria) {
  createAndExecuteSearch(criteria: $createAndExecuteSearchCriteria) {
    __typename
    ... on SearchCreateAndExecutionResponse {
      searchResponse { search { id assetType version } }
      matchResponse {
        count
        matches {
          id
          matchId
          availability { earliest latest }
          bookNow { method rate { baseRate { amount } } }
          credit { daysToPay score scoreUpdatedWhen }
          createdWhen
          modifiedWhen
          origin { area { states zones } point { city state latitude longitude deadhead { miles type } } }
          destination { area { states zones } point { city state latitude longitude deadhead { miles type } } }
          comments { comment }
          factoring
          isAssurable
          isFromPrivateNetwork
          poster { city state company contact { email phone { number extension countryCode } } }
          postersReferenceId
          postingId
          rate { baseRate { amount currency } rateBasedOn assessorials { chargeType charge { amount currency } } }
          relevance
          status
          tripLength { distanceMiles type }
          specs { lengthInFeet weightInPounds requiredCapacity requiredEquipmentType }
          version
        }
      }
    }
    ... on SearchCreateSuccessButExecutionError {
      search { id assetType version }
      error { statusCode errors { statusCode message appName } }
    }
    ... on RequestError { error { statusCode errors { statusCode message appName } } }
    ... on ServerError { error { statusCode errors { statusCode message appName } } }
  }
}
"""

_DETAILS = """
query LoadDetails($rateDetailsCriteria: LoadDetailsCriteria!) {
  searchLoadDetailsWithRates {
    searchLoadDetails(detailsCriteria: $rateDetailsCriteria) {
      __typename
      ... on LoadDetailsResponse {
        searchLoadDetails {
          id
          matchId
          dotIds { brokerMcNumber carrierMcNumber dotNumber }
          peerRatingSummary { averageRating numberOfRatings }
        }
      }
      ... on RequestError { error { statusCode errors { statusCode message appName } } }
      ... on ServerError { error { statusCode errors { statusCode message appName } } }
    }
  }
}
"""

_EQUIPMENT = {
    "v": "V",
    "van": "V",
    "r": "R",
    "reefer": "R",
    "f": "F",
    "flat": "F",
    "flatbed": "F",
    "sd": "SD",
    "step": "SD",
    "stepdeck": "SD",
    "step deck": "SD",
}

GraphqlTransport = Callable[[str, str, str, dict[str, Any]], dict[str, Any]]


class BoardError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def _dig_token(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("eyJ") and text.count(".") == 2:
            return text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ""
        return _dig_token(parsed)
    if isinstance(value, dict):
        for key in ("access_token", "accessToken", "id_token"):
            found = _dig_token(value.get(key))
            if found:
                return found
        for child in value.values():
            found = _dig_token(child)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _dig_token(child)
            if found:
                return found
    return ""


def _stream(user: dict[str, Any]) -> dict[str, Any]:
    streams = user.get("streams") or {}
    one = streams.get("one") or {}
    return one if isinstance(one, dict) else {}


def _token_from_user(user: dict[str, Any]) -> str:
    raw = _stream(user).get("lst") or "{}"
    if not isinstance(raw, str):
        raw = json.dumps(raw)
    return _dig_token(raw)


def _cookie_header(user: dict[str, Any]) -> str:
    parts: list[str] = []
    store = _stream(user).get("store") or []
    if not isinstance(store, list):
        return ""
    for cookie in store:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        if not name:
            continue
        parts.append(f"{name}={cookie.get('value') or ''}")
    return "; ".join(parts)


def board_login(username: str) -> tuple[str, str]:
    """Bearer token and cookie header for this Laneora user's board session."""
    wanted = username.strip().lower()
    ordered: list[dict[str, Any]] = []
    for user in load_local_users():
        if str(user.get("username") or "").lower() == wanted:
            ordered.insert(0, user)
        else:
            ordered.append(user)
    for user in ordered:
        token = _token_from_user(user)
        if token:
            return token, _cookie_header(user)
    raise BoardError(
        "No board session is stored yet. Capture it on the admin PC, then sign in to Laneora once.",
        409,
    )


def _proxies() -> dict[str, str] | None:
    proxy = (load_config().get("shared_proxy") or {})
    host = str(proxy.get("px") or "none")
    if host.lower() in ("", "none", "direct", "local"):
        return None
    user = str(proxy.get("pu") or "")
    password = str(proxy.get("pd") or "")
    port = str(proxy.get("p") or "0")
    auth = f"{user}:{password}@" if user or password else ""
    url = f"http://{auth}{host}:{port}"
    return {"http": url, "https": url}


def post_graphql(token: str, cookie: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if cookie:
        headers["Cookie"] = cookie
    try:
        response = requests.post(
            BOARD_GRAPHQL,
            headers=headers,
            json={"query": query, "variables": variables},
            proxies=_proxies(),
            timeout=30,
        )
    except requests.RequestException as exc:
        raise BoardError("The board did not answer.") from exc
    if response.status_code in (401, 403):
        raise BoardError("The board session expired. Capture it again on the admin PC.", 409)
    try:
        payload = response.json()
    except ValueError as exc:
        raise BoardError("The board returned something other than JSON.") from exc
    if not isinstance(payload, dict):
        raise BoardError("The board returned something other than JSON.")
    if response.status_code >= 400:
        raise BoardError(_error_text(payload) or f"Board request failed ({response.status_code}).")
    errors = payload.get("errors")
    if errors:
        message = ""
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            message = str(errors[0].get("message") or "")
        raise BoardError(message or "The board rejected the search.")
    return payload


def _error_text(payload: dict[str, Any]) -> str:
    errors = payload.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict) and item.get("message"):
                return str(item["message"])
    return ""


def _equipment(raw: Any) -> list[str]:
    if raw in (None, "", []):
        return ["V"]
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(part).strip() for part in raw if str(part).strip()]
    else:
        raise ValueError("Equipment must be a list of types, such as V, R, or F.")
    if not items:
        raise ValueError("Name at least one equipment type.")
    classes: list[str] = []
    for item in items:
        key = item.lower()
        if key in _EQUIPMENT:
            code = _EQUIPMENT[key]
        elif item.isalpha() and 1 <= len(item) <= 3:
            code = item.upper()
        else:
            raise ValueError(f"Unknown equipment '{item}'. Use V, R, F, or a DAT equipment class.")
        if code not in classes:
            classes.append(code)
    return classes


def _place(node: Any, label: str) -> dict[str, Any] | None:
    if node in (None, "", {}):
        return None
    if isinstance(node, str):
        city, _, state = node.partition(",")
        node = {"city": city.strip(), "state": state.strip()}
    if not isinstance(node, dict):
        raise ValueError(f"{label} must be a city and state, or a list of states.")
    states = node.get("states")
    if isinstance(states, str):
        states = [part.strip() for part in states.split(",") if part.strip()]
    if states:
        clean = [str(state).strip().upper() for state in states if str(state).strip()]
        if not clean:
            raise ValueError(f"{label} needs at least one state.")
        area: dict[str, Any] = {"states": clean}
        zones = node.get("zones")
        if zones:
            area["zones"] = zones
        return {"area": area}
    city = str(node.get("city") or "").strip()
    state = str(node.get("state") or node.get("state_province") or "").strip().upper()
    if not city or not state:
        raise ValueError(f"{label} needs a city and state, or a list of states.")
    point: dict[str, Any] = {"city": city, "state": state}
    if node.get("latitude") not in (None, "") and node.get("longitude") not in (None, ""):
        point["latitude"] = float(node["latitude"])
        point["longitude"] = float(node["longitude"])
    miles = node.get("deadhead_miles", node.get("deadhead"))
    if miles not in (None, ""):
        point["deadhead"] = {"miles": int(miles), "type": "ROAD"}
    return {"point": point}


def _when(value: Any, *, end: bool) -> str:
    text = str(value or "").strip()
    if not text:
        day = datetime.now(timezone.utc).date()
        if end:
            day = day + timedelta(days=1)
        text = day.isoformat()
    if len(text) == 10:
        text = text + ("T23:59:59Z" if end else "T00:00:00Z")
    return text


def search_variables(body: dict[str, Any]) -> dict[str, Any]:
    origin = _place(body.get("origin"), "Origin")
    if origin is None:
        raise ValueError("Origin is required.")
    destination = _place(body.get("destination"), "Destination")
    capacity = str(body.get("capacity") or "BOTH").strip().upper()
    if capacity not in ("BOTH", "FULL", "PARTIAL"):
        raise ValueError("Capacity must be BOTH, FULL, or PARTIAL.")
    try:
        limit = int(body.get("limit") or 100)
        max_age = int(body.get("max_age_minutes") or body.get("maxAgeMinutes") or 240)
    except (TypeError, ValueError) as exc:
        raise ValueError("Limit and max age must be numbers.") from exc
    limit = min(max(limit, 1), 500)
    max_age = min(max(max_age, 1), 10080)
    specs: dict[str, Any] = {"capacity": capacity, "equipmentClasses": _equipment(body.get("equipment"))}
    criteria: dict[str, Any] = {
        "availability": {
            "earliest": _when(body.get("earliest"), end=False),
            "latest": _when(body.get("latest"), end=True),
        },
        "desiredSpecs": specs,
        "maxAgeInMinutes": max_age,
        "origin": origin,
    }
    if destination is not None:
        criteria["destination"] = destination
    return {
        "createAndExecuteSearchCriteria": {
            "limit": limit,
            "lookbackMinutes": max_age,
            "searchCriteria": criteria,
        }
    }


def _point(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    point = node.get("point") if isinstance(node.get("point"), dict) else {}
    area = node.get("area") if isinstance(node.get("area"), dict) else {}
    deadhead = point.get("deadhead") if isinstance(point.get("deadhead"), dict) else {}
    return {
        "city": point.get("city") or "",
        "state": point.get("state") or "",
        "states": area.get("states") or [],
        "latitude": point.get("latitude"),
        "longitude": point.get("longitude"),
        "deadhead_miles": deadhead.get("miles"),
    }


def public_load(match: dict[str, Any]) -> dict[str, Any]:
    poster = match.get("poster") if isinstance(match.get("poster"), dict) else {}
    contact = poster.get("contact") if isinstance(poster.get("contact"), dict) else {}
    phone = contact.get("phone") if isinstance(contact.get("phone"), dict) else {}
    rate = match.get("rate") if isinstance(match.get("rate"), dict) else {}
    base = rate.get("baseRate") if isinstance(rate.get("baseRate"), dict) else {}
    trip = match.get("tripLength") if isinstance(match.get("tripLength"), dict) else {}
    specs = match.get("specs") if isinstance(match.get("specs"), dict) else {}
    credit = match.get("credit") if isinstance(match.get("credit"), dict) else {}
    comments = match.get("comments") if isinstance(match.get("comments"), list) else []
    comment_text = [str(item.get("comment")) for item in comments if isinstance(item, dict) and item.get("comment")]
    amount = base.get("amount")
    miles = trip.get("distanceMiles")
    per_mile = None
    if isinstance(amount, (int, float)) and isinstance(miles, (int, float)) and miles:
        per_mile = round(float(amount) / float(miles), 2)
    return {
        "id": match.get("matchId") or match.get("id") or "",
        "posting_id": match.get("postingId") or "",
        "origin": _point(match.get("origin")),
        "destination": _point(match.get("destination")),
        "availability": match.get("availability") or {},
        "equipment": specs.get("requiredEquipmentType") or "",
        "capacity": specs.get("requiredCapacity") or "",
        "length_ft": specs.get("lengthInFeet"),
        "weight_lbs": specs.get("weightInPounds"),
        "miles": miles,
        "rate": amount,
        "currency": base.get("currency") or "",
        "rate_per_mile": per_mile,
        "company": poster.get("company") or "",
        "city": poster.get("city") or "",
        "state": poster.get("state") or "",
        "phone": phone.get("number") or "",
        "phone_extension": phone.get("extension") or "",
        "email": contact.get("email") or "",
        "credit_score": credit.get("score"),
        "days_to_pay": credit.get("daysToPay"),
        "comments": comment_text,
        "reference": match.get("postersReferenceId") or "",
        "created_when": match.get("createdWhen") or "",
        "detail": match,
    }


def _raise_payload_error(node: Any) -> None:
    if not isinstance(node, dict):
        return
    error = node.get("error")
    if not isinstance(error, dict):
        return
    messages = error.get("errors")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        text = str(messages[0].get("message") or "")
        if text:
            raise BoardError(text)
    raise BoardError("The board rejected the search.")


def search_loads(username: str, body: dict[str, Any], *, transport: GraphqlTransport | None = None) -> dict[str, Any]:
    token, cookie = board_login(username)
    variables = search_variables(body)
    send = transport or post_graphql
    payload = send(token, cookie, _SEARCH, variables)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    result = data.get("createAndExecuteSearch") if isinstance(data.get("createAndExecuteSearch"), dict) else {}
    typename = str(result.get("__typename") or "")
    if typename != "SearchCreateAndExecutionResponse":
        _raise_payload_error(result)
        raise BoardError("The board did not return loads.")
    search = ((result.get("searchResponse") or {}).get("search") or {})
    matches_node = result.get("matchResponse") if isinstance(result.get("matchResponse"), dict) else {}
    matches = matches_node.get("matches") if isinstance(matches_node.get("matches"), list) else []
    loads = [public_load(match) for match in matches if isinstance(match, dict)]
    return {
        "ok": True,
        "search_id": search.get("id") or "",
        "count": matches_node.get("count") if matches_node.get("count") is not None else len(loads),
        "loads": loads,
    }


def load_detail(
    username: str,
    search_id: str,
    match_id: str,
    *,
    transport: GraphqlTransport | None = None,
) -> dict[str, Any]:
    search_id = search_id.strip()
    match_id = match_id.strip()
    if not search_id or not match_id:
        raise ValueError("search_id and match_id are required.")
    token, cookie = board_login(username)
    send = transport or post_graphql
    payload = send(
        token,
        cookie,
        _DETAILS,
        {"rateDetailsCriteria": {"searchId": search_id, "matchId": match_id}},
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    wrapper = data.get("searchLoadDetailsWithRates") if isinstance(data.get("searchLoadDetailsWithRates"), dict) else {}
    node = wrapper.get("searchLoadDetails") if isinstance(wrapper.get("searchLoadDetails"), dict) else {}
    if str(node.get("__typename") or "") != "LoadDetailsResponse":
        _raise_payload_error(node)
        raise BoardError("The board did not return that load.")
    detail = node.get("searchLoadDetails") if isinstance(node.get("searchLoadDetails"), dict) else {}
    dots = detail.get("dotIds") if isinstance(detail.get("dotIds"), dict) else {}
    rating = detail.get("peerRatingSummary") if isinstance(detail.get("peerRatingSummary"), dict) else {}
    return {
        "ok": True,
        "search_id": search_id,
        "id": detail.get("matchId") or match_id,
        "dot": {
            "broker_mc": dots.get("brokerMcNumber") or "",
            "carrier_mc": dots.get("carrierMcNumber") or "",
            "dot_number": dots.get("dotNumber") or "",
        },
        "peer_rating": {
            "average": rating.get("averageRating"),
            "count": rating.get("numberOfRatings"),
        },
        "detail": detail,
    }
