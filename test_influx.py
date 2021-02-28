from influxdb import InfluxDBClient
import dateutil.parser
import datetime

dbClient = InfluxDBClient('fitlet', 8086, 'admin', 'admin', 'hc2_log')
records = dbClient.query("select * from \"hc2\" where \"room\"='Woonkamer' order by time desc limit 1;")
for measurement in records.get_points():
    time = measurement["time"]
    time = dateutil.parser.isoparse(time)
    if (datetime.datetime.now(datetime.timezone.utc) - time).total_seconds() < 60 * 60:
        print("measurement can be used")
    humidity = measurement["humidity"]
    temperature = measurement["temperature"]
    print(measurement)
