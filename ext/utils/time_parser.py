import datetime


async def parse_time(time):
	delta = datetime.timedelta()
	if "d" in time:
		d, time = time.split("d")
		delta += datetime.timedelta(days=int(d))
	if "h" in time:
		h, time = time.split("h")
		delta += datetime.timedelta(hours=int(h))
	if "m" in time:
		m, time = time.split("m")
		delta += datetime.timedelta(minutes=int(m))
	if "s" in time:
		s = time.split("s")[0]
		delta += datetime.timedelta(seconds=int(s))
	return delta
