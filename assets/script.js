// assets/script.js
document.addEventListener('DOMContentLoaded', () => {
    
    // Animação "Fade In" para elementos com a classe
    const fadeElements = document.querySelectorAll('.fade-in');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
            }
        });
    }, { threshold: 0.1 });

    fadeElements.forEach(el => {
        observer.observe(el);
    });

    // --- Funcionalidade do Formulário de Personalização ---
    // Esta função pega o produto escolhido na URL (ex: ?produto=discord)
    // e o pré-seleciona no formulário.
    const urlParams = new URLSearchParams(window.location.search);
    const produtoEscolhido = urlParams.get('produto');
    
    const selectProduto = document.getElementById('produto-escolhido');
    
    if (selectProduto && produtoEscolhido) {
        // Tenta encontrar a <option> com o valor e selecioná-la
        const option = selectProduto.querySelector(`option[value="${produtoEscolhido}"]`);
        if (option) {
            option.selected = true;
        }
    }

    // O CÓDIGO DE SIMULAÇÃO DO PAGAMENTO FOI REMOVIDO DAQUI.
    // Agora o link <a href="..."> vai funcionar.

});