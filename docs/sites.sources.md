# 地点数据来源与现场校准

更新时间：2026-10-18

## 坐标系

`data/sites.json` 统一保存 **WGS-84**。高德、腾讯地图使用 GCJ-02，接入前需要在 A 的代码里做一次转换；不要把两种坐标混用。

百度百科词条里的静态地图中心是 **BD-09**。本文件中的 WGS-84 值用标准 BD-09 → GCJ-02 → WGS-84 公式换算，属于地图中心点，不是实测控制点。

## 三个站点

| siteId | 名称 | 公开来源 | 原始中心（BD-09） | WGS-84（本仓库） | 已核实 | 尚未核实 |
|---|---|---|---|---|---|---|
| `gaoqiao-mangrove` | 高桥红树林 | [百度百科：高桥红树林保护区](https://wapbaike.baidu.com/item/%E9%AB%98%E6%A1%A5%E7%BA%A2%E6%A0%91%E6%9E%97%E4%BF%9D%E6%8A%A4%E5%8C%BA)、[CERN 湿地条目](https://wiki.biodiversity.cern.ac.cn/index.php?title=%E6%B9%9B%E6%B1%9F%E5%B8%82%E9%AB%98%E6%A1%A5%E7%BA%A2%E6%A0%91%E6%9E%97%E6%B9%BF%E5%9C%B0)、[OSM relation 7610416](https://www.openstreetmap.org/relation/7610416) | 109.770194, 21.564385 | 109.759370, 21.561075 | 站点中心、800 米栈道、瞭望塔、观鸟亭/观林亭的名称 | 栈道拐点、瞭望塔和观鸟亭的精确坐标 |
| `texing-island` | 特呈岛红树林 | [百度百科：特呈岛](https://wapbaike.baidu.com/item/%E7%89%B9%E5%91%88%E5%B2%9B/8161704)、[特呈岛游记（600 米栈道/两端亭台）](https://www.meipian.cn/5nc6j9f3)、[OSM way 13946986](https://www.openstreetmap.org/way/13946986) | 110.439508, 21.163333 | 110.428452, 21.159749 | 站点中心、600 米栈道、两条栈道尽头的观鸟亭/观鸟台 | 栈道入口、分叉点、两个端点的精确坐标 |
| `jinniu-island` | 金牛岛红树林 | [百度百科：金牛岛红树林](https://wapbaike.baidu.com/item/%E9%87%91%E7%89%9B%E5%B2%9B%E7%BA%A2%E6%A0%91%E6%9E%97)、[广东省林业局报道](https://lyj.gd.gov.cn/news/newspaper/content/post_4221586.html)、[OSM relation 17431403](https://www.openstreetmap.org/relation/17431403) | 110.267574, 21.085486 | 110.256817, 21.081841 | 站点中心、科普广场、栈道码头、观鸟平台；位置在麻章区湖光镇世乔村 | 栈道入口、码头、观鸟平台的精确坐标 |

## 为什么 `route` 和 `birdWatchingShelters` 还是空数组

公开资料能确认“有 800 米栈道”“有两条 600 米栈道和端点亭台”“有科普广场/栈道码头/观鸟平台”，但没有公开的逐点坐标。用卫星图或地图中心猜出来的折线会再次变成“示意路线”，可能把游客带到水里或围塘里，所以本版不填假点。

`data/sites.json` 的 `description` 已明确写“待现场 GPS 校准”；`data/test_sites_data.py` 会在路线或观鸟屋为空时检查这句话，防止把未采集的数据当成已完成。

## 现场采集清单

每个站点至少采以下点，统一用 WGS-84、手机 GPS 连续读 3 次取平均，记录精度：

1. 停车场/入口/门楼
2. 栈道起点
3. 栈道每个转折点或分叉点（每 100–200 米一个）
4. 栈道终点/码头
5. 每个观鸟亭、观鸟台、瞭望塔
6. 卫生间/出口（可选，但建议）

同时拍一张带时间戳的现场照片，记录潮位和天气。回到仓库后：

1. 把点填进 `data/sites.json` 的 `route` 和 `birdWatchingShelters`；
2. 删除对应 `description` 里的“待现场 GPS 校准”；
3. 运行：

   ```bash
   python data/test_sites_data.py -v
   ```

4. 如果使用高德/腾讯地图，在 A 的代码里把 WGS-84 转成 GCJ-02，不要直接混用。

在完成现场校准前，前端不要用空路线做转弯导航；只显示站点标记和“路线待采集”提示。
