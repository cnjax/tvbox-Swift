package com.github.catvod.crawler;

public class SpiderApi {
    public String getAddress(boolean local) { return "http://127.0.0.1:" + getPort(); }
    public String getPort() { return System.getProperty("bridge.port", "9978"); }
    public void log(String msg) { SpiderDebug.log(msg); }
    public String multiReq(com.google.gson.JsonArray reqs) { return "[]"; }
    public String webParse(String url, String flag) { return ""; }
}
