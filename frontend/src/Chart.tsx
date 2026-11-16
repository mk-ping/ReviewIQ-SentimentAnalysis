import { useEffect, useRef } from "react";
import * as echarts from "echarts";

const axis = {
  axisLine: { lineStyle: { color: "#303545" } },
  axisTick: { lineStyle: { color: "#303545" } },
  axisLabel: { color: "#8a92a6" },
  splitLine: { lineStyle: { color: "#232733" } },
  nameTextStyle: { color: "#8a92a6" },
};
echarts.registerTheme("reviewiq", {
  color: ["#8b7bff", "#22d3ee", "#34d399", "#f5b83d", "#fb7185", "#60a5fa"],
  backgroundColor: "transparent",
  textStyle: { color: "#a7aebf" },
  title: { textStyle: { color: "#f2f4f8" } },
  legend: { textStyle: { color: "#a7aebf" } },
  tooltip: { backgroundColor: "#171a22", borderColor: "#303545", textStyle: { color: "#f2f4f8" } },
  categoryAxis: axis,
  valueAxis: axis,
  timeAxis: axis,
});

export default function Chart({ option, height = 260 }: { option: echarts.EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, "reviewiq");
    c.setOption(option);
    const onResize = () => c.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); c.dispose(); };
  }, [option]);
  return <div ref={ref} style={{ height, width: "100%" }} />;
}
