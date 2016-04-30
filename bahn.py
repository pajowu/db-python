import requests
from hashlib import md5
import base64
import json
from Crypto.Cipher import AES
import codecs
import datetime
import re
class BahnAPI():
    debug = False
    base_url = "http://reiseauskunft.bahn.de/bin/mgate.exe?checksum={checksum}"
    redtnCards = {"25_1": 1, "25_2": 2, "50_1": 3, "50_2": 4}
    traveler_types = {"adult": "E", "child": "K", "infant": "B"}
    def searchLocation(self, term):
        data = {"svcReqL":[{"meth":"LocMatch","req":{"input":{"field":"S","loc":{"name":term}}}}]}
        search_request = self.sendPostRequest(data)
        response = self.cleanResponse(search_request.json())
        search_results = []
        if response["cInfo"]["code"] == "OK":
            for response_part in response["svcResL"]:
                if response_part["err"] == "OK" and response_part["meth"] == "LocMatch":
                    for result in response_part["res"]["match"]["locL"]:
                        search_results.append({k:v for k,v in result.items() if k in ["lid", "name", "type"]}) # filter to only include lib, name and type field
        return search_results

    def searchTrip(self, start, end, start_datetime=datetime.datetime.now(), travelers=[("adult", None)], ctx=None):
        search_results = {"results":[]}
        real_start = self.searchLocation(start)[0]
        real_end = self.searchLocation(end)[0]
        traveler_profiles = [{"type":self.traveler_type[traveler[0]]} if traveler[1] == None else {"type":self.traveler_types[traveler[0]], "redtnCard":self.redtnCards[traveler[1]]} for traveler in travelers]
        data = {"svcReqL":[{"cfg":{"polyEnc":"GPA"},"meth":"TripSearch","req":{"outDate":start_datetime.strftime("%Y%m%d"),"outTime":start_datetime.strftime("%H%M%S"),"arrLocL":[real_end],"depLocL":[real_start],"getPasslist":True,"trfReq":{"tvlrProf":traveler_profiles}, "frwd": True }}]}
        if ctx:
            data["svcReqL"][0]["req"]["ctxScr"] = ctx
        search_request = self.sendPostRequest(data)
        response = self.cleanResponse(search_request.json())

        if self.debug:
            print(json.dumps(response, indent=4))

        if response["cInfo"]["code"] == "OK":
            for response_part in response["svcResL"]:
                if response_part["err"] == "OK" and response_part["meth"] == "TripSearch":
                    commons = response_part["res"]["common"]
                    search_results["ctx_earlier"] = response_part["res"]["outCtxScrB"]
                    search_results["ctx_later"] = response_part["res"]["outCtxScrF"]
                    for result in response_part["res"]["outConL"]:
                        result_dict ={
                            "days_binary":''.join(format(x, 'b').zfill(8) for x in codecs.decode(result["sDays"]["sDaysB"], "hex")), # each bit is a day of the year
                            "days_human":result["sDays"]["sDaysI"] if "sDaysI" in result["sDays"] else "",
                            "departure": {
                                "time": self.getFinalTime(result["date"], result["dep"]["dTimeS"]),
                                "platform": result["dep"]["dPlatfS"],
                                "stop": real_start
                            },
                            "arrival": {
                                "time": self.getFinalTime(result["date"], result["arr"]["aTimeS"]),
                                "platform": result["arr"]["aPlatfS"],
                                "stop": real_end
                            },
                            "duration": datetime.timedelta(hours=int(result["dur"][:-4]), minutes=int(result["dur"][-4:-2]), seconds=int(result["dur"][-2:])),
                            "sections":[]
                            }
                        if "trfRes" in result:
                            fares = []
                            for fareSet in result["trfRes"]["fareSetL"]:
                                for fare in fareSet["fareL"]:
                                    fare["price"] = fare["prc"]/100
                                    fares.append(fare)
                            result_dict["fares"] = fares
                        for section in result["secL"]:
                            section_dict =  {
                                "departure": {
                                    "time": self.getFinalTime(result["date"], result["dep"]["dTimeS"]),
                                    "platform": section["dep"]["dPlatfS"],
                                    "location": commons["locL"][section["dep"]["locX"]]["name"]
                                },
                                "arrival": {
                                    "time": self.getFinalTime(result["date"], result["arr"]["aTimeS"]),
                                    "platform": section["arr"]["aPlatfS"],
                                    "location": commons["locL"][section["arr"]["locX"]]["name"]
                                },
                                "stops": []
                            }
                            section_dict["duration"] = section_dict["arrival"]["time"] - section_dict["departure"]["time"]

                            for stop in section["jny"]["stopL"]:
                                loc = commons["locL"][stop["locX"]]
                                stop_dict = {
                                    "stop":loc,
                                    "platform": stop["aPlatfS"] if "aPlatfS" in stop else stop["dPlatfS"] if "dPlatfS" in stop else None
                                }
                                if "dTimeS" in stop: stop_dict["departure"] =  {"time": self.getFinalTime(result["date"], stop["dTimeS"])}
                                if "aTimeS" in stop: stop_dict["arrival"] =  {"time": self.getFinalTime(result["date"], stop["aTimeS"])}
                            result_dict["sections"].append(section_dict)
                        search_results["results"].append(result_dict)

        return search_results

    def parse_timedelta(self, time_str):
        regex = re.compile(r'(?P<days>\d{2})(?P<hours>\d{2})(?P<minutes>\d{2})(?P<seconds>\d{2})')
        if len(time_str) == 6:
            time_str = "00"+time_str
        parts = regex.match(time_str)
        if not parts:
            return
        parts = parts.groupdict()
        time_params = {name:int(amount) for name, amount in parts.items()}
        return datetime.timedelta(**time_params)

    def getFinalTime(self, start_date, duration):
        dur = self.parse_timedelta(duration)
        return datetime.datetime.strptime(start_date, "%Y%m%d") + dur

    def sendPostRequest(self, data, headers={}):
        data["auth"] = {"aid":"n91dB8Z77MLdoR0K","type":"AID"} # from res/raw/haf_config.properties of DBNavigator
        data["client"] = {"id":"DB","name":"DB Navigator","type":"AND","v":15120000}
        data["ver"] = "1.10"
        data["ext"] = "DB.R15.12.a"
        data = json.dumps(data)
        chk = self.generateChecksum(data)
        url = self.base_url.format(checksum = chk)
        request = requests.post(url, data=data)
        return request

    def cleanResponse(self, data):
        return data

    def generateChecksum(self, data):
        to_hash = data + self.getSecret()
        to_hash = to_hash.encode("utf-8")
        return md5(to_hash).hexdigest()

    def getSecret(self):
        unpad = lambda s : s[:-ord(s[len(s)-1:])] # http://stackoverflow.com/a/12525165/3890934
        enc = base64.b64decode("rGhXPq+xAlvJd8T8cMnojdD0IoaOY53X7DPAbcXYe5g=") # from res/raw/haf_config.properties of DBNavigator
        key = bytes([97, 72, 54, 70, 56, 122, 82, 117, 105, 66, 110, 109, 51, 51, 102, 85]) # from de/hafas/g/a/b.java of DBNavigator
        iv = codecs.decode("00"*16, "hex")
        cipher = AES.new(key, AES.MODE_CBC, iv)
        dec = unpad(cipher.decrypt(enc).decode("utf-8"))
        return dec

if __name__ == "__main__":
    api = BahnAPI()
    res = api.searchTrip("Leipzig", "Berlin")
    print(res)