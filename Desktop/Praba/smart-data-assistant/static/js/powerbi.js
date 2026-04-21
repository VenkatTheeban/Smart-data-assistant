let mainChart = null;
let currentFilters = {
    year: 'All',
    months: [],
    customs: []
};
let isFirstLoad = true;

document.addEventListener('DOMContentLoaded', () => {
    Chart.register(ChartDataLabels);

    fetchData();

    document.getElementById('year-slicer').addEventListener('change', (e) => {
        currentFilters.year = e.target.value;
        fetchData();
    });

    document.getElementById('month-slicer').addEventListener('change', (e) => {
        const selected = Array.from(e.target.selectedOptions).map(opt => opt.value);
        currentFilters.months = selected.filter(v => v !== 'Multiple selections');
        fetchData();
    });

    const customBtns = document.querySelectorAll('.custom-btn');
    customBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const val = e.target.textContent;
            if (currentFilters.customs.includes(val)) {
                currentFilters.customs = currentFilters.customs.filter(v => v !== val);
                e.target.style.background = '#fff';
                e.target.style.color = '#333';
            } else {
                currentFilters.customs.push(val);
                e.target.style.background = '#666';
                e.target.style.color = '#fff';
            }
            fetchData();
        });
    });

    const clearBtn = document.querySelector('.clear-slicers button');
    clearBtn.addEventListener('click', () => {
        currentFilters = { year: 'All', months: [], customs: [] };
        document.getElementById('year-slicer').value = 'All';
        document.getElementById('month-slicer').selectedIndex = -1;
        customBtns.forEach(btn => {
            btn.style.background = '#fff';
            btn.style.color = '#333';
        });
        fetchData();
    });
});

function fetchData() {
    fetch('/api/data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(currentFilters)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error(data.error);
            document.getElementById('kpi-value').textContent = 'ERR';
            return;
        }

        if (data.warning) {
            console.warn(data.warning);
        }

        if (isFirstLoad) {
            const yearSlicer = document.getElementById('year-slicer');
            if (data.filters.years.length > 0) {
                yearSlicer.innerHTML = `<option>All</option>` + data.filters.years.map(y => `<option>${y}</option>`).join('');
            }

            const monthSlicer = document.getElementById('month-slicer');
            if (data.filters.months.length > 0) {
                monthSlicer.setAttribute('multiple', 'true');
                monthSlicer.style.height = '60px';
                monthSlicer.innerHTML = data.filters.months.map(m => `<option value="${m}">${m}</option>`).join('');
            }
            isFirstLoad = false;
        }

        document.getElementById('kpi-value').textContent = data.kpi;

        const actTbody = document.getElementById('activation-tbody');
        let actHtml = '';
        for (const [type, count] of Object.entries(data.activation_table)) {
            actHtml += `<tr><td>${type}</td><td class="right-align">${count}</td></tr>`;
        }
        actTbody.innerHTML = actHtml;
        document.getElementById('activation-total').textContent = data.raw_total;

        const moTbody = document.getElementById('monthly-tbody');
        let moHtml = '';
        data.monthly_table.forEach(row => {
            moHtml += `<tr><td>${row.month}</td><td class="right-align">${row.total}</td></tr>`;
        });
        moTbody.innerHTML = moHtml;
        document.getElementById('monthly-total').textContent = data.raw_total;

        renderChart(data);
    })
    .catch(err => console.error(err));
}

function renderChart(data) {
    const ctx = document.getElementById('mainChart').getContext('2d');
    const datasetOrder = ['Different Device Used', 'New Installation', 'Reactivation'];

    let globalMax = 0;
    datasetOrder.forEach(label => {
        if (data.chart_datasets[label]) {
            data.chart_datasets[label].forEach(val => {
                if (val > globalMax) globalMax = val;
            });
        }
    });

    const datasets = datasetOrder.map(label => {
        return {
            label,
            data: data.chart_datasets[label] || [],
            backgroundColor: '#a3112e',
            barPercentage: 0.85,
            categoryPercentage: 0.8
        };
    });

    if (mainChart) {
        mainChart.destroy();
    }

    mainChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.chart_labels,
            datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                datalabels: {
                    anchor: 'end',
                    align: (context) => {
                        const val = context.dataset.data[context.dataIndex];
                        return val < (globalMax * 0.25) ? 'end' : 'start';
                    },
                    offset: (context) => {
                        const val = context.dataset.data[context.dataIndex];
                        return val < (globalMax * 0.25) ? 6 : 2;
                    },
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    borderRadius: 4,
                    padding: {
                        top: 3,
                        bottom: 3,
                        left: 6,
                        right: 6
                    },
                    color: '#000',
                    font: { weight: 'bold', size: 10 },
                    formatter: (value) => Math.round(value)
                }
            },
            scales: {
                x: {
                    grid: { display: false, drawBorder: true },
                    ticks: { display: false }
                },
                y: {
                    display: false,
                    suggestedMax: globalMax * 1.3,
                    grid: { display: false }
                }
            },
            layout: {
                padding: { top: 40, bottom: 120 }
            }
        },
        plugins: [{
            id: 'customPowerBIStyle',
            afterDraw(chart) {
                const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
                ctx.save();

                x.ticks.forEach((tick, index) => {
                    const groupCenterX = x.getPixelForTick(index);
                    const groupWidth = x.width / Math.max(1, x.ticks.length);
                    const groupLeft = groupCenterX - (groupWidth / 2);

                    ctx.font = '13px "Segoe UI", sans-serif';
                    ctx.fillStyle = '#333';
                    ctx.textAlign = 'left';
                    ctx.textBaseline = 'bottom';
                    const monthText = data.chart_labels[index];
                    ctx.fillText(monthText, groupLeft + 10, top - 10);

                    if (index > 0) {
                        ctx.beginPath();
                        ctx.moveTo(groupLeft, top - 30);
                        ctx.lineTo(groupLeft, bottom + 120);
                        ctx.lineWidth = 1;
                        ctx.strokeStyle = '#c0c0c0';
                        ctx.stroke();
                    }
                });

                ctx.font = '11px "Segoe UI", sans-serif';
                ctx.fillStyle = '#444';
                ctx.textAlign = 'right';
                ctx.textBaseline = 'middle';

                chart.data.datasets.forEach((dataset, i) => {
                    const meta = chart.getDatasetMeta(i);
                    meta.data.forEach((bar) => {
                        ctx.save();
                        ctx.translate(bar.x, bottom + 10);
                        ctx.rotate(-Math.PI / 2);
                        ctx.fillText(dataset.label, 0, 0);
                        ctx.restore();
                    });
                });

                ctx.restore();
            }
        }]
    });
}
