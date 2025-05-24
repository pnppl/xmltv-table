#!/bin/python3
import argparse
from datetime import datetime, timedelta, UTC
import requests
import subprocess

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument("-u", "--html_url", type=str, help="url of html table to parse (or optional data source annotation if using --fromfile)")
group.add_argument("-f", "--fromfile", type=str, help="name of file to parse instead of URL")
parser.add_argument("-n", "--site_name", type=str, help="name of the streaming channel", default="Swim Rewind")
parser.add_argument("-s", "--site_url", type=str, help="URL of channel homepage", default="https://swimrewind.com/")
parser.add_argument("-c", "--channel", type=str, help="channel id (should match m3u8)", default="sr")
parser.add_argument("-w", "--weeks", type=int, help="how many weeks of EPG to generate", default=1)
parser.add_argument("-t", "--tz_offset", type=float, help="hours to offset local time to get UTC; eg EDT = 4", default=0) # SR = 5, CDT
parser.add_argument("-o", "--outfile", type=str, help="where to write results")
parser.add_argument("-k", "--key", type=str, help="TMDB API key")
args = parser.parse_args()
headers = {
	"accept": "application/json",
	"Authorization": f"Bearer {args.key}" 
}
if args.outfile == None:
	args.outfile = args.site_name + '-schedule.xmltv'
try:
	fileout = open(args.outfile, 'w')
except:
	print("couldn't write to fileout")
	exit(1)

mon, tue, wed, thu, fri, sat, sun = [], [], [], [], [], [], []
now = datetime.now(UTC)
now_day = now.weekday()
tmdb_base_url = ''
tmdb_genres = {}
tmdb_cache = {}

def request(url):
	return requests.get(url, headers=headers)

def tmdb_init():
	global tmdb_base_url
	global tmdb_genres
	url = "https://api.themoviedb.org/3/configuration"
	tmdb_base_url = request(url).json()['images']['secure_base_url']
	url = "https://api.themoviedb.org/3/genre/tv/list"
	tv = request(url).json()['genres']
	url = "https://api.themoviedb.org/3/genre/movie/list"
	movie = request(url).json()['genres']
	for genre in tv:
		tmdb_genres[genre['id']] = genre['name'].replace('&', '&amp;')
	for genre in movie:
		tmdb_genres[genre['id']] = genre['name'].replace('&', '&amp;')

def tmdb(title):
	global tmdb_cache
	if title in tmdb_cache:
		return tmdb_cache[title]
	else:
		url = f"https://api.themoviedb.org/3/search/tv?query={title}"
		response = request(url)
		if response.json()['total_results'] == 0:
			url = f"https://api.themoviedb.org/3/search/movie?query={title}"
			response = request(url)
			if response.json()['total_results'] == 0:
				return None
		result = response.json()['results'][0]
		tmdb_cache[title] = result
		return result

def time_str_parse(time):
	try:
		return datetime.strptime(time, "%I:%M %p")
	except ValueError:
		try:
			return datetime.strptime(time, "%I:%M%p")
		except ValueError:
			try:
				return datetime.strptime(time, "%I:%M")
			except:
				print("time parse fail")
				exit(1)

# in: time range in local time as string, date in UTC
# out: beginning and end datetimes in UTC as tuple; stop is start+30 if unspecified
def time_conv(time_range, date):
	times = time_range.split(' - ')
	utc = timedelta(hours=args.tz_offset)
	start = time_str_parse(times[0])
	start = date.combine(date.date(), start.time()) + utc
	if len(times) == 1:
		return start, start + timedelta(minutes=30)
	else:	
		stop = time_str_parse(times[1])
		stop = date.combine(date.date(), stop.time()) + utc
		return start, stop

# in: [time_local, title, {meta}], date
# out: none -- writes
def programme(slot, date):
	start, stop = time_conv(slot[0], date)
	fmt = "%Y%m%d%H%M%S"
	fileout.write(f'\n <programme start="{ start.strftime(fmt) } +0000"')
#	if stop != None:
#		fileout.write(f' stop="{ stop.strftime(fmt) } +0000"')
	fileout.write(f""" channel="{ args.channel }">
  <title>{ slot[1] }</title>""")
	meta = slot[2]
	try:
#		fileout.write(f"""
#  <country>{ meta['origin_country'][0] }</country>
#  <orig-language>{ meta['original_language'] }</orig-language>
#  <star-rating system="tmdb"><value>{ meta['vote_average'] }</value></star-rating>""")
		fileout.write(f"""
  <desc>{ meta['overview'].replace('&', '&amp;').replace('<', '&lt;') }</desc>
  <icon src="{ tmdb_base_url + 'w780' + meta['poster_path'] }"></icon>""")
		try:
			fileout.write(f"\n  <date>{ meta['first_air_date'].replace('-', '') }</date>")
		except:
			fileout.write(f"\n  <date>{ meta['release_date'].replace('-', '') }</date>")
		for genre in meta['genre_ids']:
			fileout.write(f"\n  <category>{ tmdb_genres[genre] }</category>")
	except:
		print("program meta missing: " + str(slot))
	fileout.write("\n </programme>")

# hacky bullshit to replace later maybe
basename = f'_!_{args.site_name}_schedule_!_'
def shell_init():
	if args.fromfile == None:
		try:
			subprocess.run(f"wget '{args.html_url}' -O '{basename}.html'", shell=True, check=True)	
		except:
			print("couldn't download schedule; right url?")
			exit(1)
	else:
		try:
			subprocess.run(f"cp '{args.fromfile}' '{basename}.html'", shell=True, check=True)	
		except:
			print("couldn't find input file")
			exit(1)
	try:
		subprocess.run(f"libreoffice --convert-to tsv:'Text' '{basename}.html' && rm '{basename}.html'", shell=True, check=True)
	except:
		print("couldn't convert with libreoffice lol")
		exit(1)
	try:
		subprocess.run(f"cat '{basename}.tsv' | grep -e '[0-9]:[0-9][0-9]' > '{basename}.tmp' && mv '{basename}.tmp' '{basename}.tsv'", shell=True, check=True)
	except:
		print("couldn't use fucking grep")
		exit(1)


shell_init()
tmdb_init()

try:
	filein = open(f"{basename}.tsv", 'r')
except:
	print("cleaned tsv missing")
	exit(1)
for row in filein:
	cells = row.rstrip('\n').rstrip(' ').split('\t')
	if len(cells) == 9:
		_ = cells.pop(0)
	if len(cells) == 8:
		try:
			time_local = cells.pop(0)
			for day in range(7):
				out = [time_local, cells[day], tmdb(cells[day])]
				match day:
					case 0:
						mon.append(out)
					case 1:
						tue.append(out)
					case 2:
						wed.append(out)
					case 3:
						thu.append(out)
					case 4:
						fri.append(out)
					case 5:
						sat.append(out)
					case 6:
						sun.append(out)
		except ValueError:
			print("line fail: " + str(cells))
week = [mon, tue, wed, thu, fri, sat, sun]
fileout.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<tv date="{ now.strftime("%Y-%d-%m") }" source-info-url="{args.site_url}" source-info-name="{args.site_name}" source-data-url="{args.html_url}" generator-info-name="python3">
 <channel id="{args.channel}">
  <display-name>{args.site_name}</display-name>
 </channel>""")
for i in range(args.weeks * 7):
	weekday = (now_day + i) % 7
	date = now + timedelta(days=i)
	for slot in week[weekday]:
		programme(slot, date)
fileout.write('\n</tv>')
fileout.flush()
fileout.close()
filein.close()