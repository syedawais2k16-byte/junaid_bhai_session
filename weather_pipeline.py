#Installing Libraries

import requests
import pandas as pd
import clickhouse_connect 


#Calling the API
base_url = "https://archive-api.open-meteo.com/v1/archive"
params = { "latitude": 19.43,
           "longitude": -99.13,
           "start_date": "2026-10-01",
           "end_date": "2026-10-30",
            "hourly": "temperature_2m",
            "timezone": "America/Mexico_City",
}
response = requests.get(base_url, params=params, timeout=10)
response.raise_for_status()
data = response.json()

#Table-1 for hourly data per day suing pandas dataframe
hourly = pd.DataFrame(data["hourly"])

hourly["datetime"] = pd.to_datetime(hourly["time"], format="%Y-%m-%dT%H:%M")
hourly["date"] = hourly["datetime"].dt.date
hourly["time"] = hourly["datetime"].dt.strftime("%H:%M") 

hourly = hourly[["datetime", "date", "time", "temperature_2m"]]

print("Hourly rows:", len(hourly))         # expect 720
print(hourly.head())

# ---------- 3. TABLE 2: min and max per day, with the time each happened ----------
min_rows = hourly.loc[hourly.groupby("date")["temperature_2m"].idxmin()]    # coldest hour of each day
max_rows = hourly.loc[hourly.groupby("date")["temperature_2m"].idxmax()]    # hottest hour of each day

min_rows = min_rows[["date", "temperature_2m", "time"]].rename(
    columns={"temperature_2m": "temp_min", "time": "min_time"})
max_rows = max_rows[["date", "temperature_2m", "time"]].rename(
    columns={"temperature_2m": "temp_max", "time": "max_time"})

daily = min_rows.merge(max_rows, on="date")                                 # one row per day

print("Daily rows:", len(daily))           # expect 30
print(daily.head())

# ---------- 4. LOAD into ClickHouse ----------
client = clickhouse_connect.get_client(host="localhost", port=8123,
                                       username="admin", password="Admin123")

client.command("CREATE DATABASE IF NOT EXISTS weather")

# drop and recreate, so every run starts clean with the right columns
client.command("DROP TABLE IF EXISTS weather.mexico_hourly")
client.command("DROP TABLE IF EXISTS weather.mexico_daily")

client.command("""
    CREATE TABLE weather.mexico_hourly (
        datetime        DateTime,
        date            Date,
        time            String,
        temperature_2m  Float64
    )
    ENGINE = MergeTree
    ORDER BY datetime
""")

client.command("""
    CREATE TABLE weather.mexico_daily (
        date      Date,
        temp_min  Float64,
        min_time  String,
        temp_max  Float64,
        max_time  String
    )
    ENGINE = MergeTree
    ORDER BY date
""")

client.insert_df("mexico_hourly", hourly, database="weather")
client.insert_df("mexico_daily", daily, database="weather")

# ---------- 5. VERIFY ----------
print("ClickHouse hourly rows:", client.command("SELECT count() FROM weather.mexico_hourly"))
print("ClickHouse daily rows :", client.command("SELECT count() FROM weather.mexico_daily"))
print("ClickHouse min/max:", client.query("SELECT min(temp_min), max(temp_max) FROM weather.mexico_daily").result_rows)
print("pandas min/max    :", daily["temp_min"].min(), daily["temp_max"].max())