import requests
import datetime
from dateutil.tz import gettz
import json

url = "https://api.tomorrow.io/v4/timelines"

querystring = {
    "location": "6138471889c05400076aafc4",
    "fields": ["temperature", "precipitationIntensity", "windSpeed", "windDirection"],
    "units": "metric",
    "timesteps": ["current", "1h"],
    "startTime": datetime.datetime.now(gettz("Europe/Amsterdam")).isoformat(),
    "endTime": (datetime.datetime.now(gettz("Europe/Amsterdam")) + datetime.timedelta(hours = 6)).isoformat(),
    "apikey": "FhO5tMdZBkoUDgIMahAECTo7us4nDFKy"
}

response = requests.request("GET", url, params=querystring)
print(response.text)
data = json.loads(response.text)
print(data["data"]["timelines"][0]["intervals"][0]["values"]["temperature"])
