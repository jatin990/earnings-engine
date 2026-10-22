/**
 * Canvas Charts: High-DPI interactive HTML5 Canvas charts with responsive crosshair HUDs.
 */
(function() {
    window.app = window.app || {};
    const app = window.app;

    app.drawSparklineChart = function(canvasId, values, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !values || values.length < 2) return;

        const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 300, height: 100 };
        const dpr = Math.max(window.devicePixelRatio || 1, 2);
        const w = Math.round(rect.width || 300);
        const h = Math.round(rect.height || 100);

        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';

        const ctx = canvas.getContext('2d');

        const minVal = options.minVal !== undefined ? options.minVal : Math.min(...values) * 0.98;
        const maxVal = options.maxVal !== undefined ? options.maxVal : Math.max(...values) * 1.02;
        const valRange = (maxVal - minVal) || 1.0;

        const padding = 10;
        const drawW = w - padding * 2;
        const drawH = h - padding * 2;

        // Calculate points
        const points = values.map((v, i) => {
            const x = padding + (i / (values.length - 1)) * drawW;
            const y = padding + drawH - ((v - minVal) / valRange) * drawH;
            const date = options.dates && options.dates[i] ? options.dates[i] : '';
            return { x, y, v, date, index: i };
        });

        const renderFrame = (hoverPoint = null) => {
            ctx.save();
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, w, h);

            // Draw Reference Corridor Lines
            if (options.referenceLines) {
                options.referenceLines.forEach((ref, idx) => {
                    if (ref >= minVal && ref <= maxVal) {
                        const y = padding + drawH - ((ref - minVal) / valRange) * drawH;
                        ctx.beginPath();
                        ctx.strokeStyle = (options.refLineColors && options.refLineColors[idx]) || 'rgba(255,255,255,0.12)';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([3, 3]);
                        ctx.moveTo(padding, y);
                        ctx.lineTo(w - padding, y);
                        ctx.stroke();
                        ctx.setLineDash([]);
                    }
                });
            }

            // Fill Area Gradient
            const gradient = ctx.createLinearGradient(0, padding, 0, h - padding);
            gradient.addColorStop(0, options.gradientFrom || 'rgba(56,189,248,0.28)');
            gradient.addColorStop(1, options.gradientTo || 'rgba(56,189,248,0.01)');

            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (let i = 1; i < points.length; i++) {
                const prev = points[i - 1];
                const curr = points[i];
                const cpX = (prev.x + curr.x) / 2;
                ctx.bezierCurveTo(cpX, prev.y, cpX, curr.y, curr.x, curr.y);
            }
            ctx.lineTo(points[points.length - 1].x, h - padding);
            ctx.lineTo(points[0].x, h - padding);
            ctx.closePath();
            ctx.fillStyle = gradient;
            ctx.fill();

            // Stroke Line
            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (let i = 1; i < points.length; i++) {
                const prev = points[i - 1];
                const curr = points[i];
                const cpX = (prev.x + curr.x) / 2;
                ctx.bezierCurveTo(cpX, prev.y, cpX, curr.y, curr.x, curr.y);
            }
            ctx.strokeStyle = options.color || '#38bdf8';
            ctx.lineWidth = 2.0;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.stroke();

            if (hoverPoint) {
                // Vertical Crosshair
                ctx.beginPath();
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
                ctx.lineWidth = 1;
                ctx.setLineDash([2, 2]);
                ctx.moveTo(hoverPoint.x, padding);
                ctx.lineTo(hoverPoint.x, h - padding);
                ctx.stroke();
                ctx.setLineDash([]);

                // Glowing Hover Dot
                ctx.beginPath();
                ctx.arc(hoverPoint.x, hoverPoint.y, 4.5, 0, Math.PI * 2);
                ctx.fillStyle = '#ffffff';
                ctx.shadowColor = options.color || '#38bdf8';
                ctx.shadowBlur = 10;
                ctx.fill();
                ctx.shadowBlur = 0;
                ctx.lineWidth = 2;
                ctx.strokeStyle = options.color || '#38bdf8';
                ctx.stroke();

                // Micro-HUD Tooltip Pill
                const valText = options.valueFormatter ? options.valueFormatter(hoverPoint.v) : hoverPoint.v.toFixed(1);
                const hudText = hoverPoint.date ? `${hoverPoint.date} · ${valText}` : `${valText}`;
                ctx.font = '600 9px var(--font-mono, monospace)';
                const textWidth = ctx.measureText(hudText).width;
                const pillW = textWidth + 12;
                const pillH = 16;
                let pillX = Math.min(Math.max(hoverPoint.x - pillW / 2, padding), w - padding - pillW);
                let pillY = hoverPoint.y - 20;
                if (pillY < padding) pillY = hoverPoint.y + 8;

                ctx.fillStyle = 'rgba(10, 15, 29, 0.88)';
                ctx.strokeStyle = options.color || '#38bdf8';
                ctx.lineWidth = 1;
                ctx.beginPath();
                if (typeof ctx.roundRect === 'function') {
                    ctx.roundRect(pillX, pillY, pillW, pillH, 3);
                } else {
                    ctx.rect(pillX, pillY, pillW, pillH);
                }
                ctx.fill();
                ctx.stroke();

                ctx.fillStyle = '#f8fafc';
                ctx.fillText(hudText, pillX + 6, pillY + 11);
            } else {
                // Glowing Last Point
                const last = points[points.length - 1];
                ctx.beginPath();
                ctx.arc(last.x, last.y, 3.5, 0, Math.PI * 2);
                ctx.fillStyle = options.color || '#38bdf8';
                ctx.shadowColor = options.color || '#38bdf8';
                ctx.shadowBlur = 8;
                ctx.fill();
                ctx.shadowBlur = 0;
            }

            ctx.restore();
        };

        // Initial render
        renderFrame();

        // Interactive Crosshair Listeners
        canvas.onmousemove = (e) => {
            const cRect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - cRect.left;
            let closest = points[0];
            let minDist = Math.abs(points[0].x - mouseX);
            for (let i = 1; i < points.length; i++) {
                const dist = Math.abs(points[i].x - mouseX);
                if (dist < minDist) {
                    minDist = dist;
                    closest = points[i];
                }
            }
            renderFrame(closest);
        };

        canvas.onmouseleave = () => {
            renderFrame(null);
        };
    };

    app.drawMultiLineChart = function(canvasId, datasets, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !datasets || !datasets.length) return;

        const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 300, height: 100 };
        const dpr = Math.max(window.devicePixelRatio || 1, 2);
        const w = Math.round(rect.width || 300);
        const h = Math.round(rect.height || 100);

        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';

        const ctx = canvas.getContext('2d');

        let allVals = [];
        datasets.forEach(ds => { allVals = allVals.concat(ds.values || []); });
        if (allVals.length === 0) return;

        const minVal = Math.min(...allVals);
        const maxVal = Math.max(...allVals);
        const valRange = (maxVal - minVal) || 1.0;

        const padding = 10;
        const drawW = w - padding * 2;
        const drawH = h - padding * 2;

        const preparedDatasets = datasets.map(ds => {
            const vals = ds.values || [];
            const points = vals.map((v, i) => {
                const x = padding + (i / (vals.length - 1)) * drawW;
                const y = padding + drawH - ((v - minVal) / valRange) * drawH;
                const date = options.dates && options.dates[i] ? options.dates[i] : '';
                return { x, y, v, date, index: i };
            });
            return { ...ds, points };
        });

        const renderFrame = (hoverIndex = null) => {
            ctx.save();
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, w, h);

            // Zero line
            if (options.showZeroLine && minVal <= 0 && maxVal >= 0) {
                const zeroY = padding + drawH - ((0 - minVal) / valRange) * drawH;
                ctx.beginPath();
                ctx.strokeStyle = 'rgba(255,255,255,0.18)';
                ctx.lineWidth = 1;
                ctx.setLineDash([2, 2]);
                ctx.moveTo(padding, zeroY);
                ctx.lineTo(w - padding, zeroY);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Draw each dataset curve
            preparedDatasets.forEach(ds => {
                const points = ds.points;
                if (points.length < 2) return;

                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                for (let i = 1; i < points.length; i++) {
                    const prev = points[i - 1];
                    const curr = points[i];
                    const cpX = (prev.x + curr.x) / 2;
                    ctx.bezierCurveTo(cpX, prev.y, cpX, curr.y, curr.x, curr.y);
                }
                ctx.strokeStyle = ds.color || '#38bdf8';
                ctx.lineWidth = 1.8;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.stroke();

                if (hoverIndex === null) {
                    const last = points[points.length - 1];
                    ctx.beginPath();
                    ctx.arc(last.x, last.y, 3, 0, Math.PI * 2);
                    ctx.fillStyle = ds.color || '#38bdf8';
                    ctx.fill();
                }
            });

            if (hoverIndex !== null) {
                const samplePt = preparedDatasets[0]?.points[hoverIndex];
                if (samplePt) {
                    // Crosshair
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([2, 2]);
                    ctx.moveTo(samplePt.x, padding);
                    ctx.lineTo(samplePt.x, h - padding);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Highlight dots
                    preparedDatasets.forEach(ds => {
                        const pt = ds.points[hoverIndex];
                        if (pt) {
                            ctx.beginPath();
                            ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
                            ctx.fillStyle = '#ffffff';
                            ctx.shadowColor = ds.color || '#38bdf8';
                            ctx.shadowBlur = 8;
                            ctx.fill();
                            ctx.shadowBlur = 0;
                            ctx.lineWidth = 2;
                            ctx.strokeStyle = ds.color || '#38bdf8';
                            ctx.stroke();
                        }
                    });

                    // Multi-line HUD
                    const dateStr = samplePt.date || '';
                    let hudItems = preparedDatasets.map(ds => {
                        const pt = ds.points[hoverIndex];
                        const vStr = pt ? (options.valueFormatter ? options.valueFormatter(pt.v) : pt.v.toLocaleString()) : '—';
                        return `${ds.name}: ${vStr}`;
                    });
                    const hudText = (dateStr ? `[${dateStr}] ` : '') + hudItems.join(' · ');
                    ctx.font = '600 9px var(--font-mono, monospace)';
                    const textWidth = ctx.measureText(hudText).width;
                    const pillW = textWidth + 12;
                    const pillH = 16;
                    let pillX = Math.min(Math.max(samplePt.x - pillW / 2, padding), w - padding - pillW);
                    let pillY = padding + 2;

                    ctx.fillStyle = 'rgba(10, 15, 29, 0.90)';
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    if (typeof ctx.roundRect === 'function') {
                        ctx.roundRect(pillX, pillY, pillW, pillH, 3);
                    } else {
                        ctx.rect(pillX, pillY, pillW, pillH);
                    }
                    ctx.fill();
                    ctx.stroke();

                    ctx.fillStyle = '#f8fafc';
                    ctx.fillText(hudText, pillX + 6, pillY + 11);
                }
            }

            ctx.restore();
        };

        // Initial render
        renderFrame();

        // Interactive Crosshair Listeners
        canvas.onmousemove = (e) => {
            const cRect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - cRect.left;
            const samplePoints = preparedDatasets[0]?.points || [];
            if (!samplePoints.length) return;

            let closestIdx = 0;
            let minDist = Math.abs(samplePoints[0].x - mouseX);
            for (let i = 1; i < samplePoints.length; i++) {
                const dist = Math.abs(samplePoints[i].x - mouseX);
                if (dist < minDist) {
                    minDist = dist;
                    closestIdx = i;
                }
            }
            renderFrame(closestIdx);
        };

        canvas.onmouseleave = () => {
            renderFrame(null);
        };
    };
})();
