import requests
from hashlib import md5
import base64
import json
from Crypto.Cipher import AES
import codecs
import datetime
class BahnAPI():
    base_url = "http://reiseauskunft.bahn.de/bin/mgate.exe?checksum={checksum}"
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

    def searchTrip(self, start, end, start_datetime=datetime.datetime.now(), **kwargs):
        search_results = []
        real_start = self.searchLocation(start)[0]
        real_end = self.searchLocation(end)[0]
        data = {"svcReqL":[{"cfg":{"polyEnc":"GPA"},"meth":"TripSearch","req":{"outDate":start_datetime.strftime("%Y%m%d"),"outTime":start_datetime.strftime("%H%M%S"),"arrLocL":[real_end],"cMZE":0,"depLocL":[real_start],"economic":False,"extChgTime":-1,"frwd":True,"getEco":False,"getIST":False,"getIV":False,"getPT":True,"getPasslist":True,"getPolyline":True,"getTariff":True,"indoor":False,"liveSearch":False,"maxChg":1000,"maxChgTime":-1,"minChgTime":-1,"supplChgTime":-1,"trfReq":{"cType":"PK","jnyCl":2,"tvlrProf":[{"type":"E"}]},"ushrp":False}}]}
        search_request = self.sendPostRequest(data)
        response = self.cleanResponse(search_request.json())

        if response["cInfo"]["code"] == "OK":
            for response_part in response["svcResL"]:
                if response_part["err"] == "OK" and response_part["meth"] == "TripSearch":
                    commons = response_part["res"]["common"]
                    for result in response_part["res"]["outConL"]:
                        result_dict ={
                            "days_binary":''.join(format(x, 'b').zfill(8) for x in codecs.decode(result["sDays"]["sDaysB"], "hex")), # each bit is a day of the year
                            "days_human":result["sDays"]["sDaysI"],
                            "departure": {
                                "time": datetime.datetime.strptime(result["date"]+result["dep"]["dTimeS"], "%Y%m%d%H%M%S"),
                                "platform": result["dep"]["dPlatfS"],
                                "stop": real_start
                            },
                            "arrival": {
                                "time": datetime.datetime.strptime(result["date"]+result["arr"]["aTimeS"], "%Y%m%d%H%M%S"),
                                "platform": result["arr"]["aPlatfS"],
                                "stop": real_end
                            },
                            "duration": datetime.timedelta(hours=int(result["dur"][:-4]), minutes=int(result["dur"][-4:-2]), seconds=int(result["dur"][-2:])),
                            "sections":[]}

                        for section in result["secL"]:
                            section_dict =  {
                                "departure": {
                                    "time": datetime.datetime.strptime(result["date"]+section["dep"]["dTimeS"], "%Y%m%d%H%M%S"),
                                    "platform": section["dep"]["dPlatfS"]
                                },
                                "arrival": {
                                    "time": datetime.datetime.strptime(result["date"]+section["arr"]["aTimeS"], "%Y%m%d%H%M%S"),
                                    "platform": section["arr"]["aPlatfS"]
                                },
                                "stops": []
                            }
                            section_dict["duration"] = section_dict["arrival"]["time"] - section_dict["departure"]["time"]

                            for stop in section["jny"]["stopL"]:
                                loc = commons["locL"][stop["locX"]]
                                stop_dict = {
                                    "stop":loc,
                                    "platform": stop["aPlatfS"] if "aPlatfS" in stop else stop["dPlatfS"]
                                }
                                if "dTimeS" in stop: stop_dict["departure"] =  {"time": datetime.datetime.strptime(result["date"]+stop["dTimeS"], "%Y%m%d%H%M%S")}
                                if "aTimeS" in stop: stop_dict["arrival"] =  {"time": datetime.datetime.strptime(result["date"]+stop["aTimeS"], "%Y%m%d%H%M%S")}
                            result_dict["sections"].append(section_dict)
                        search_results.append(result_dict)

        return search_results


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