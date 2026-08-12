import { useEffect, useRef } from "react";

type Props = {
  analyser: AnalyserNode | null;
  live: boolean;
  side: "A" | "B" | null;
};

export function Scope({ analyser, live, side }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let frame = 0;
    const buffer = new Uint8Array(256);

    const draw = () => {
      frame = requestAnimationFrame(draw);
      const { width, height } = canvas;
      ctx.fillStyle = "#06040c";
      ctx.fillRect(0, 0, width, height);

      const stroke = side === "B" ? "#ff2d95" : "#2de2ff";
      const soft = side === "B" ? "rgba(255,45,149,0.2)" : "rgba(45,226,255,0.18)";

      ctx.strokeStyle = soft;
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();

      if (!analyser || !live) {
        ctx.strokeStyle = stroke;
        ctx.globalAlpha = 0.45;
        ctx.beginPath();
        ctx.moveTo(8, height / 2);
        ctx.lineTo(width - 8, height / 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
        return;
      }

      analyser.getByteTimeDomainData(buffer);
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1.6;
      ctx.shadowColor = stroke;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      for (let i = 0; i < buffer.length; i++) {
        const v = buffer[i] / 128 - 1;
        const x = (i / (buffer.length - 1)) * width;
        const y = height / 2 + v * (height * 0.4);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;
    };

    draw();
    return () => cancelAnimationFrame(frame);
  }, [analyser, live, side]);

  return <canvas ref={canvasRef} className="scope" width={200} height={72} aria-hidden />;
}
