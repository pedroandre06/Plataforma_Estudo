/* Plataforma de Estudos - interações leves (sem dependências) */
(function () {
  "use strict";

  /* ---------------------------------------------- alternativas do quiz */
  document.querySelectorAll(".js-quiz").forEach(function (form) {
    var opcoes = form.querySelectorAll(".js-opcao");
    opcoes.forEach(function (label) {
      label.addEventListener("click", function () {
        opcoes.forEach(function (o) { o.classList.remove("ativo"); });
        label.classList.add("ativo");
      });
    });
  });

  /* ------------------------------------------ atalhos de teclado (1-5) */
  var quiz = document.querySelector(".js-quiz");
  if (quiz) {
    document.addEventListener("keydown", function (ev) {
      if (ev.target.tagName === "TEXTAREA" || ev.target.tagName === "INPUT") {
        if (ev.key === "Enter" && ev.target.type === "radio") { quiz.submit(); }
        return;
      }
      var n = parseInt(ev.key, 10);
      var radios = quiz.querySelectorAll('input[type="radio"]');
      if (n >= 1 && n <= radios.length) {
        radios[n - 1].checked = true;
        radios[n - 1].dispatchEvent(new Event("change", { bubbles: true }));
        var label = radios[n - 1].closest(".js-opcao");
        quiz.querySelectorAll(".js-opcao").forEach(function (o) { o.classList.remove("ativo"); });
        if (label) { label.classList.add("ativo"); }
      }
    });
  }

  /* ------------------------------------------------------- flashcards */
  document.querySelectorAll(".flashcard").forEach(function (carta) {
    carta.addEventListener("click", function () { carta.classList.toggle("virado"); });
  });

  /* -------------------------------------------------- simulado/prova */
  var execucao = document.getElementById("execucao");
  if (!execucao) { return; }

  var tid = execucao.dataset.tid;
  var form = document.getElementById("form-simulado");
  var restante = parseInt(execucao.dataset.restante || "0", 10);
  var relogio = document.querySelector(".js-restante");
  var entregue = false;

  function marcarGrade(perguntaId, dados) {
    var botao = document.querySelector('.grade-questoes button[data-pergunta="' + perguntaId + '"]');
    if (!botao) { return; }
    if (dados && dados.marcada !== undefined) {
      botao.classList.toggle("marcada", !!dados.marcada);
    }
    if (dados && dados.respondida !== undefined) {
      botao.classList.toggle("respondida", !!dados.respondida);
    }
  }

  function enviar(payload) {
    return fetch("/api/simulado/" + tid + "/resposta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); });
  }

  document.querySelectorAll('.grade-questoes button[data-alvo]').forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alvo = document.getElementById(botao.dataset.alvo);
      if (alvo) { alvo.scrollIntoView({ behavior: "smooth", block: "start" }); }
      document.querySelectorAll(".grade-questoes button")
        .forEach(function (b) { b.classList.remove("atual"); });
      botao.classList.add("atual");
    });
  });

  document.querySelectorAll('.js-marcar').forEach(function (botao) {
    botao.addEventListener("click", function () {
      var perguntaId = botao.dataset.pergunta;
      var marcada = botao.dataset.marcada === "1" ? 0 : 1;
      botao.dataset.marcada = String(marcada);
      botao.textContent = marcada ? "★ Marcada para revisar" : "☆ Marcar para revisar";
      marcarGrade(perguntaId, { marcada: marcada });
      enviar({ pergunta_id: parseInt(perguntaId, 10), marcar: marcada });
    });
  });

  document.querySelectorAll('#form-simulado input[type="radio"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      var perguntaId = radio.name.replace("p_", "");
      var card = radio.closest(".card");
      if (card) {
        card.querySelectorAll(".alternativa").forEach(function (a) { a.classList.remove("ativo"); });
        var label = radio.closest(".alternativa");
        if (label) { label.classList.add("ativo"); }
      }
      marcarGrade(perguntaId, { respondida: 1 });
      enviar({ pergunta_id: parseInt(perguntaId, 10), alternativa_id: parseInt(radio.value, 10) });
    });
  });

  document.querySelectorAll(".js-entrega").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var respondidas = document.querySelectorAll('#form-simulado input[type="radio"]:checked').length;
      var total = document.querySelectorAll('#form-simulado input[type="radio"]').length;
      var faltam = Math.max(0, total - respondidas);
      var texto = faltam > 0
        ? "Ainda faltam " + faltam + " questões sem resposta. Entregar mesmo assim?"
        : "Entregar o simulado agora?";
      if (window.confirm(texto)) {
        entregue = true;
        form.submit();
      }
    });
  });

  if (relogio && restante > 0) {
    var inicio = Date.now();
    var apagar = setInterval(function () {
      var decorrido = Math.floor((Date.now() - inicio) / 1000);
      var resta = restante - decorrido;
      if (resta <= 0) {
        clearInterval(apagar);
        if (relogio) { relogio.textContent = "00:00"; }
        if (!entregue) {
          entregue = true;
          var campo = document.getElementById("tempo_seg");
          if (campo) { campo.value = String(restante + decorrido); }
          window.alert("Tempo esgotado! O simulado será entregue automaticamente.");
          form.submit();
        }
        return;
      }
      var min = String(Math.floor(resta / 60)).padStart(2, "0");
      var seg = String(resta % 60).padStart(2, "0");
      relogio.textContent = min + ":" + seg;
      if (resta <= 300) { relogio.classList.add("alerta"); }
    }, 1000);
  }
})();
