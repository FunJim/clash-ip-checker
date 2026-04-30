"""IP geolocation lookup via ipinfo.io."""
import aiohttp
from typing import Dict, Optional


COUNTRY_CN_MAP = {
    "US": "美国", "HK": "香港", "TW": "台湾", "JP": "日本", "KR": "韩国",
    "SG": "新加坡", "GB": "英国", "UK": "英国", "DE": "德国", "FR": "法国",
    "NL": "荷兰", "RU": "俄罗斯", "CA": "加拿大", "AU": "澳大利亚", "IN": "印度",
    "BR": "巴西", "IT": "意大利", "ES": "西班牙", "CH": "瑞士", "SE": "瑞典",
    "NO": "挪威", "FI": "芬兰", "DK": "丹麦", "BE": "比利时", "AT": "奥地利",
    "IE": "爱尔兰", "PL": "波兰", "CZ": "捷克", "HU": "匈牙利", "RO": "罗马尼亚",
    "GR": "希腊", "PT": "葡萄牙", "TR": "土耳其", "UA": "乌克兰", "IL": "以色列",
    "AE": "阿联酋", "SA": "沙特", "ZA": "南非", "EG": "埃及", "MX": "墨西哥",
    "AR": "阿根廷", "CL": "智利", "CO": "哥伦比亚", "PE": "秘鲁", "TH": "泰国",
    "VN": "越南", "MY": "马来西亚", "PH": "菲律宾", "ID": "印尼", "CN": "中国",
    "MO": "澳门", "NZ": "新西兰", "IS": "冰岛", "LU": "卢森堡", "PA": "巴拿马",
    "MD": "摩尔多瓦", "LT": "立陶宛", "LV": "拉脱维亚", "EE": "爱沙尼亚",
    "BG": "保加利亚", "SK": "斯洛伐克", "SI": "斯洛文尼亚", "HR": "克罗地亚",
    "RS": "塞尔维亚", "KZ": "哈萨克斯坦", "AM": "亚美尼亚", "GE": "格鲁吉亚",
    "AZ": "阿塞拜疆", "BY": "白俄罗斯", "PK": "巴基斯坦", "BD": "孟加拉",
    "LK": "斯里兰卡", "MM": "缅甸", "KH": "柬埔寨", "MN": "蒙古", "NP": "尼泊尔",
    "LA": "老挝", "AF": "阿富汗", "IR": "伊朗", "IQ": "伊拉克", "SY": "叙利亚",
    "JO": "约旦", "LB": "黎巴嫩", "KW": "科威特", "QA": "卡塔尔", "BH": "巴林",
    "OM": "阿曼", "YE": "也门", "DZ": "阿尔及利亚", "MA": "摩洛哥", "TN": "突尼斯",
    "NG": "尼日利亚", "KE": "肯尼亚", "ET": "埃塞俄比亚", "GH": "加纳",
    "CI": "科特迪瓦", "SN": "塞内加尔", "ZW": "津巴布韦", "AO": "安哥拉",
    "VE": "委内瑞拉", "EC": "厄瓜多尔", "BO": "玻利维亚", "PY": "巴拉圭",
    "UY": "乌拉圭", "CR": "哥斯达黎加", "DO": "多米尼加", "GT": "危地马拉",
    "HN": "洪都拉斯", "SV": "萨尔瓦多", "NI": "尼加拉瓜", "CU": "古巴",
    "BS": "巴哈马", "PR": "波多黎各", "JM": "牙买加", "HT": "海地",
}


def country_flag_emoji(code: str) -> str:
    """Convert 2-letter ISO country code to flag emoji."""
    if not code or len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(ord(c) - ord("A") + 0x1F1E6) for c in code.upper())


def country_chinese_name(code: str) -> str:
    if not code:
        return "未知"
    return COUNTRY_CN_MAP.get(code.upper(), code.upper())


class GeoLookup:
    def __init__(self, token: Optional[str] = None, timeout: float = 3.0):
        self.token = token or ""
        self.timeout = timeout
        self.cache: Dict[str, Dict] = {}

    def clear_cache(self):
        self.cache.clear()

    async def lookup(self, ip: str) -> Optional[Dict]:
        """Fetch country info for an IP. Returns dict or None on failure."""
        if not ip or ip == "❓":
            return None
        if ip in self.cache:
            return self.cache[ip]

        url = f"https://ipinfo.io/{ip}/json"
        params = {"token": self.token} if self.token else None

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    code = (data.get("country") or "").upper()
                    if not code:
                        return None
                    info = {
                        "country_code": code,
                        "country_name": country_chinese_name(code),
                        "country_flag": country_flag_emoji(code),
                    }
                    self.cache[ip] = info
                    return info
        except Exception as e:
            print(f"     [Geo] Lookup failed for {ip}: {e}")
            return None
