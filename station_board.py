from bahn import BahnAPI
api = BahnAPI()
print(api.stationBoard("Braunschweig Hbf",duration=120))
