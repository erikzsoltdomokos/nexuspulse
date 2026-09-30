// Tree-shaken ECharts setup plus a small React hook that owns an instance.
import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { HeatmapChart, LineChart, RadarChart, ScatterChart } from 'echarts/charts';
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  HeatmapChart,
  LineChart,
  RadarChart,
  ScatterChart,
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

export { echarts };
export type EChartsInstance = ReturnType<typeof echarts.init>;

/**
 * Creates an ECharts instance on the returned ref, applies `option` whenever it
 * changes and keeps the canvas sized to its container.
 */
export function useEChart(
  option: echarts.EChartsCoreOption | null,
  onInit?: (chart: EChartsInstance) => void,
  notMerge = true,
) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsInstance | null>(null);
  const onInitRef = useRef(onInit);
  onInitRef.current = onInit;

  const roRef = useRef<ResizeObserver | null>(null);

  // Lazily (re)initialise so a container that mounts late or is replaced still works.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let chart = chartRef.current;
    if (!chart || chart.isDisposed() || chart.getDom() !== el) {
      chart?.dispose();
      roRef.current?.disconnect();
      chart = echarts.init(el, undefined, { renderer: 'canvas' });
      chartRef.current = chart;
      const c = chart;
      roRef.current = new ResizeObserver(() => c.resize());
      roRef.current.observe(el);
      onInitRef.current?.(chart);
    }
    if (option) chart.setOption(option, { notMerge });
  }, [option, notMerge]);

  useEffect(
    () => () => {
      roRef.current?.disconnect();
      roRef.current = null;
      chartRef.current?.dispose();
      chartRef.current = null;
    },
    [],
  );

  return { ref, chartRef };
}
