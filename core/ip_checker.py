import asyncio
import re
import aiohttp
from typing import Optional, Dict

# Strategies
from .sources.ping0 import Ping0Source
from .sources.ippure import IPPureSource
from .sources.browser import BrowserSource
from .geo import GeoLookup

class IPChecker:
    def __init__(self, headless=True, ipinfo_token: str = ""):
        self._headless = headless

        # Components
        self.ping0 = Ping0Source()
        self.ippure = IPPureSource()
        self.browser_source = BrowserSource(headless=headless)
        self.geo = GeoLookup(token=ipinfo_token)

        self.cache = {} # Map IP -> Result Dict

    def clear_cache(self):
        """Clears the IP result cache."""
        self.cache.clear()
        self.geo.clear_cache()
        print("[IPChecker] Cache cleared.")

    async def _augment_geo(self, result: Dict):
        """Augment result with country info from ipinfo.io (in place)."""
        if not result:
            return
        if "country_code" in result:
            return  # already augmented
        ip = result.get("ip")
        if not ip or ip == "❓":
            return
        geo = await self.geo.lookup(ip)
        if not geo:
            return
        result.update(geo)
        # Append country info inside 【...】 as |中文名🇺🇸】
        suffix = f"|{geo['country_name']}{geo['country_flag']}"
        fs = result.get("full_string", "")
        if fs.endswith("】"):
            result["full_string"] = fs[:-1] + suffix + "】"
        elif fs:
            result["full_string"] = f"{fs}【{suffix[1:]}】"
        else:
            result["full_string"] = f"【{suffix[1:]}】"

    @property
    def headless(self):
        return self._headless

    @headless.setter
    def headless(self, value):
        self._headless = value
        self.browser_source.headless = value

    async def start(self):
        await self.browser_source.start()

    async def stop(self):
        await self.browser_source.stop()

    async def get_simple_ip(self, proxy=None):
        """Fast IPv4 check - races candidate URLs in parallel, returns first valid IP."""
        urls = ["http://api.ipify.org", "http://v4.ident.me"]

        async def fetch(url):
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, proxy=proxy) as resp:
                    if resp.status != 200:
                        raise ValueError(f"status {resp.status}")
                    ip = (await resp.text()).strip()
                    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                        raise ValueError("invalid ip format")
                    return ip

        tasks = [asyncio.create_task(fetch(u)) for u in urls]
        try:
            for coro in asyncio.as_completed(tasks):
                try:
                    return await coro
                except Exception:
                    continue
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
        return None

    # --- Main Interface ---

    async def check_browser(self, url="https://ippure.com/", proxy=None, timeout=20000):
        """Full browser check"""
        
        # 1. Cleaner Fast IP & Cache Logic
        current_ip = await self.get_simple_ip(proxy)
        if current_ip and current_ip in self.cache:
            # Strict mode: Only accept cache if it has bot_score (from browser check)
            cached = self.cache[current_ip]
            if "bot_score" in cached:
                print(f"     [Cache Hit] {current_ip}")
                return cached
        
        if current_ip:
            print(f"     [New IP] {current_ip}")
        else:
            print("     [Warning] Fast IP check failed. Scanning with browser...")

        # 2. Delegate to Browser Source
        result = await self.browser_source.check(proxy)

        # Inject IP if browser failed to find it but simple check passed
        if result["ip"] == "❓" and current_ip:
            result["ip"] = current_ip

        # Augment with geo info before caching
        await self._augment_geo(result)

        # Cache Update
        if result["ip"] != "❓" and result["pure_score"] != "❓":
            self.cache[result["ip"]] = result.copy()

        return result

    async def check_fast(self, proxy=None, source="ping0", fallback=True):
        """
        Fast mode: Prioritizes source (ping0/ippure), falls back if enabled.
        Budget: up to 3s for cache pre-check + 5s primary + 5s fallback + 3s geo = ~16s worst case.
        """
        try:
            return await asyncio.wait_for(
                self._check_fast_impl(proxy, source, fallback),
                timeout=25
            )
        except asyncio.TimeoutError:
            print(f"     [check_fast] Total timeout exceeded")
            return {
                "pure_emoji": "❓", "shared_emoji": "❓", "ip_attr": "❓", "ip_src": "❓",
                "pure_score": "❓", "shared_users": "N/A", "full_string": "【⏱️ Timeout】", 
                "ip": "❓", "error": "Timeout", "source": "timeout"
            }
    
    async def _check_fast_impl(self, proxy=None, source="ping0", fallback=True):
        """Internal implementation of check_fast with prioritization"""
        # 0. Check Cache First (Optimization) + capture current proxy IP for last-resort geo
        fast_ip = None
        try:
            fast_ip = await self.get_simple_ip(proxy)
            if fast_ip and fast_ip in self.cache:
                # print(f"     [Cache Hit] {fast_ip}")
                return self.cache[fast_ip]
        except Exception:
            pass # Ignore fast check errors and proceed to normal check

        # Helper wrappers to update cache
        async def try_ping0():
            res = await self.ping0.check(proxy)
            if res and res.get("ip") and res["ip"] != "❓":
                await self._augment_geo(res)
                self.cache[res["ip"]] = res.copy()
                return res
            return None

        async def try_ippure():
            res = await self.ippure.check(proxy)
            if res and res.get("ip") and res["ip"] != "❓":
                await self._augment_geo(res)
                self.cache[res["ip"]] = res.copy()
                return res
            return None

        # Logic based on config
        primary_task = try_ping0 if source == "ping0" else try_ippure
        secondary_task = try_ippure if source == "ping0" else try_ping0

        # 1. Try Primary
        result = await primary_task()
        if result:
            return result

        # 2. Try Fallback if enabled
        if fallback:
            print(f"     [Check] {source} failed, falling back...")
            fallback_result = await secondary_task()
            if fallback_result:
                return fallback_result

        # 3. All sources failed — still emit country info if we captured the proxy IP
        fail = {
            "pure_emoji": "❓", "shared_emoji": "❓", "ip_attr": "❓", "ip_src": "❓",
            "pure_score": "❓", "shared_users": "N/A",
            "full_string": "【❌ Check Failed】",
            "ip": fast_ip or "❓",
            "error": f"All sources failed (Primary: {source})",
            "source": "failed",
        }
        if fast_ip:
            await self._augment_geo(fail)
        return fail
