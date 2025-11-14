/* admin/admin-script.js */
document.addEventListener('DOMContentLoaded', () => {

    // Destaca o link ativo na sidebar
    const currentPage = window.location.pathname.split('/').pop();
    if (currentPage) {
        const links = document.querySelectorAll('.sidebar-nav li a');
        links.forEach(link => {
            if (link.getAttribute('href').includes(currentPage)) {
                link.classList.add('active');
            }
        });
    }

    // --- Gráfico (Dashboard) ---
    const ctx = document.getElementById('order-chart');
    if (ctx) {
        
        // USA AS VARIÁVEIS GLOBAIS VINDAS DO FLASK
        // (definidas em dashboard.html)
        const data = {
            labels: chartLabels, 
            datasets: [{
                label: 'Novos Pedidos',
                data: chartData, 
                borderColor: '#FFD700', // Ouro
                backgroundColor: 'rgba(255, 215, 0, 0.1)',
                fill: true,
                tension: 0.3
            }]
        };

        // Configuração do gráfico (sem mudanças)
        new Chart(ctx, {
            type: 'line',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#E0E0E0' // Texto
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#E0E0E0' },
                        grid: { color: 'rgba(255, 215, 0, 0.1)' }
                    },
                    y: {
                        ticks: { color: '#E0E0E0' },
                        grid: { color: 'rgba(255, 215, 0, 0.1)' }
                    }
                }
            }
        });
    }
});