import re
import json
import requests
import logging
from pathlib import Path

# art module for creating ASCII Art
# from art import text2art
from rich import box
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from ansi2html import Ansi2HTMLConverter
from flask_caching import Cache
from flask import Flask, Response, request

SERVER_MAP = {
    "pub": "pub.regulars.win",
    "votable": "votable.regulars.win",
    "mars": "mars.regulars.win",
}
JSON_ENDPOINT = "https://api.regulars.win/servers/{target}"
USER_AGENTS = ["curl", "wget", "xh", "fetch"]
CACHE_DIR = Path(".").cwd() / "flask_cache"

config = {
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": str(CACHE_DIR),
    "CACHE_DEFAULT_TIMEOUT": 60,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("regulars_status")

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

ansi2html_converter = Ansi2HTMLConverter()


@cache.memoize(timeout=30)
def fetch_server_data(server_name: str):
    logger.info("Cache miss! Fetching fresh data for %s", server_name)
    response = requests.get(JSON_ENDPOINT.format(target=server_name), timeout=5)
    return response.json()


def remove_xoncolors(string: str) -> str:
    """Removes Xonotic Color Codes"""
    return re.sub(r"\^[0-9]|\^x[0-9a-fA-F]{3}", "", string)


def read_json_file(filename: str):
    with open(filename, "rb") as infile:
        return json.load(infile)


def create_status(data: dict):
    console = Console(record=True, width=60)

    with console.capture() as capture:
        hostname = data.get("host", "Unknow Server")
        map_name = data.get("map", "Unknown Map")
        game_type = data.get("info", {}).get("gametype", "N/A").upper()
        mod_name = data.get("info", {}).get("mod_name", "N/A")

        server_title = f"[bold cyan]{hostname}[/]"
        p_count = int(data.get("players_count", 0))
        p_max = int(data.get("players_max", 0))

        sv_public = int(data.get("sv_public", 0))

        if sv_public == 1:
            public = "YES"
        else:
            public = "NO"

        cpu_usage = data.get("timing", {}).get("cpu", 0)
        lost_frames = data.get("timing", {}).get("lost", 0)
        offset_avg = data.get("timing", {}).get("offset_avg", 0)
        offset_max = data.get("timing", {}).get("offset_max", 0)
        offset_sdev = data.get("timing", {}).get("offset_sdev", 0)

        meta_table = Table.grid(expand=True)
        meta_table.add_column(justify="left")
        meta_table.add_column(justify="left")
        meta_table.add_column(justify="left")
        meta_table.add_row(
            f"[yellow]Map:[/] {map_name}",
            f"[yellow]Game Type:[/] {game_type}",
            f"[yellow]Players:[/] {p_count}/{p_max}",
        )
        meta_table.add_row(
            f"[yellow]Mode Name:[/] {mod_name}",
            f"[yellow]CPU Usage:[/] {cpu_usage}%",
            f"[yellow]Lost Frames:[/] {lost_frames}%",
        )
        meta_table.add_row(
            f"[yellow]Avg Offset:[/] {offset_avg}ms",
            f"[yellow]Max Offset:[/] {offset_max}ms",
            f"[yellow]Stddev Offset:[/] {offset_sdev}",
        )

        console.print(
            Panel(
                meta_table,
                title=server_title,
                subtitle=f"Public: {public}",
                box=box.ROUNDED,
                border_style="bright_blue",
            )
        )
        console.print("[dim]" + "-" * 60 + "[/]")

        # Player status
        if p_count != 0:
            player_table = Table(
                title=f"Players [{p_count}/{p_max}]",
                box=box.ROUNDED,
                border_style="bold magenta",
                expand=True,
            )
            player_table.add_column("Name", justify="left")
            player_table.add_column("Ping", justify="right")
            player_table.add_column("PL", justify="right")
            player_table.add_column("Frags", justify="right")
            player_table.add_column("Time", justify="right")

            for player in data.get("players", []):
                if int(player.get("frags", 0)) == -666:
                    score = "[yellow]spectator[/]"
                else:
                    score = f"[green]{player.get('frags', 0)}[/]"

                player_table.add_row(
                    remove_xoncolors(player.get("name", "Unknown")),
                    f"[green]{player.get('ping', '0')}ms[/]",
                    f"[green]{player.get('pl', '0')}[/]",
                    score,
                    f"[yellow]{player.get('time', '0')}[/]",
                )
            console.print(player_table)

    return capture.get()


def status_handler(server_nick: str):
    server_nick = server_nick.lower()

    if server_nick not in SERVER_MAP:
        return Response(
            f"Error: Unknown server '{server_nick}'. Choose from {', '.join(SERVER_MAP.keys())}",
            status=404,
            mimetype="text/plain",
        )

    user_agent = request.headers.get("User-Agent", "").lower()
    target = SERVER_MAP[server_nick]

    try:
        data = fetch_server_data(target)
        ansi_status = create_status(data)

        if any(agent in user_agent for agent in USER_AGENTS):
            return Response(ansi_status, mimetype="text/plain")
        else:
            return Response(ansi2html_converter.convert(ansi_status))
    except requests.exceptions.ReadTimeout as e:
        logging.exception("Connection Timeout for %s: %s", target, e)
        return Response("Server Status temporarily unavaliable.", status=503)


@app.route("/", strict_slashes=False)
@app.route("/status", strict_slashes=False)
def default_status():
    return status_handler("pub")


@app.route("/status/<server_nick>", strict_slashes=False)
def specific_server(server_nick: str):
    return status_handler(server_nick)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
