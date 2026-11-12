import { useEffect, useRef } from "react";
import * as echarts from "echarts";

export default function Chart({ option, height = 260 }: { option: echarts.EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current);
    c.setOption(option);
    const onResize = () => c.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); c.dispose(); };
  }, [option]);
  return <div ref={ref} style={{ height, width: "100%" }} />;
}
