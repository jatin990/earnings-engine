/**
 * Chart.js configurations and rendering
 */

class ChartManager {
    constructor() {
        this.priceChart = null;
        this.chartCanvas = document.getElementById('priceChart');
    }
    
    async renderPriceChart(ticker, startDate, endDate) {
        try {
            // Show loading state
            if (this.chartCanvas) {
                this.chartCanvas.style.opacity = '0.5';
            }
            
            // Fetch price data
            const params = new URLSearchParams({
                start_date: startDate,
                end_date: endDate
            });
            
            const response = await fetch(`/api/v1/price-history/${ticker}?${params}`);
            const data = await response.json();
            
            if (!data || data.length === 0) {
                console.error('No price data available');
                return;
            }
            
            // Prepare data for chart
            const labels = data.map(d => d.date);
            const prices = data.map(d => d.close);
            const volumes = data.map(d => d.volume);
            
            // Destroy existing chart
            if (this.priceChart) {
                this.priceChart.destroy();
            }
            
            // Create new chart
            const ctx = this.chartCanvas.getContext('2d');
            this.priceChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Price',
                            data: prices,
                            borderColor: '#3B82F6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1,
                            pointRadius: 0,
                            pointHoverRadius: 5,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Volume',
                            data: volumes,
                            type: 'bar',
                            backgroundColor: 'rgba(16, 185, 129, 0.3)',
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                color: '#6b7280',
                                usePointStyle: true,
                                padding: 15
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0, 0, 0, 0.8)',
                            padding: 12,
                            titleFont: {
                                size: 13
                            },
                            bodyFont: {
                                size: 12
                            },
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed.y !== null) {
                                        if (context.dataset.type === 'bar') {
                                            label += new Intl.NumberFormat('en-US').format(context.parsed.y);
                                        } else {
                                            label += '$' + context.parsed.y.toFixed(2);
                                        }
                                    }
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                display: false
                            },
                            ticks: {
                                color: '#6b7280',
                                maxRotation: 0,
                                maxTicksLimit: 10
                            }
                        },
                        y: {
                            type: 'linear',
                            position: 'left',
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            },
                            ticks: {
                                color: '#6b7280',
                                callback: function(value) {
                                    return '$' + value.toFixed(2);
                                }
                            }
                        },
                        y1: {
                            type: 'linear',
                            position: 'right',
                            grid: {
                                display: false
                            },
                            ticks: {
                                color: '#10B981',
                                callback: function(value) {
                                    if (value >= 1000000) {
                                        return (value / 1000000).toFixed(1) + 'M';
                                    } else if (value >= 1000) {
                                        return (value / 1000).toFixed(1) + 'K';
                                    }
                                    return value;
                                }
                            }
                        }
                    }
                }
            });
            
            // Reset opacity
            if (this.chartCanvas) {
                this.chartCanvas.style.opacity = '1';
            }
            
        } catch (error) {
            console.error('Error rendering price chart:', error);
        }
    }
    
    renderEarningsChart(earningsData) {
        // Placeholder for earnings chart
        // Could show EPS estimate vs reported over time
        console.log('Earnings chart rendering not yet implemented');
    }
    
    renderScoreGauge(score) {
        // Placeholder for earnings quality score gauge
        // Could use a radial progress or gauge chart
        console.log('Score gauge rendering not yet implemented');
    }
    
    destroy() {
        if (this.priceChart) {
            this.priceChart.destroy();
            this.priceChart = null;
        }
    }
}

// Initialize chart manager
let chartManager;
document.addEventListener('DOMContentLoaded', () => {
    chartManager = new ChartManager();
});