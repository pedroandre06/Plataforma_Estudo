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
  var apiUrl = execucao.dataset.api || ("/api/simulado/" + tid + "/resposta");
  var form = document.getElementById("form-simulado") || execucao.querySelector("form");
  var chavePrefixo = apiUrl.indexOf("/api/tentativa/") === 0 ? "rascunho-tentativa-" : "rascunho-simulado-";
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
    var tentativas = 0;
    function tentar(resolve) {
      tentativas += 1;
      fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload)
      }).then(function (r) {
        return r.json();
      }).then(function (dados) {
        if (dados) { try { limparRascunho(payload); } catch (e) {} }
        resolve(dados);
      }).catch(function () {
        // Falha de rede: guarda o rascunho local e tenta de novo 1x.
        try { guardarRascunho(payload); } catch (e) {}
        if (tentativas < 2) {
          setTimeout(function () { tentar(resolve); }, 1500);
        } else { resolve(null); }
      });
    }
    return new Promise(tentar);
  }

  function chaveRascunho() { return chavePrefixo + tid; }

  function lerRascunho() {
    try { return JSON.parse(localStorage.getItem(chaveRascunho()) || "{}"); }
    catch (e) { return {}; }
  }

  function guardarRascunho(payload) {
    var atual = lerRascunho();
    if (payload && payload.pergunta_id && payload.alternativa_id !== undefined) {
      atual[String(payload.pergunta_id)] = payload.alternativa_id;
    }
    if (payload && payload.respostas) {
      Object.keys(payload.respostas).forEach(function (k) { atual[k] = payload.respostas[k]; });
    }
    localStorage.setItem(chaveRascunho(), JSON.stringify(atual));
  }

  function limparRascunho(payload) {
    if (!payload || (!payload.pergunta_id && !payload.respostas)) {
      localStorage.removeItem(chaveRascunho());
      return;
    }
    var atual = lerRascunho();
    if (payload.pergunta_id) { delete atual[String(payload.pergunta_id)]; }
    if (payload.respostas) {
      Object.keys(payload.respostas).forEach(function (k) { delete atual[k]; });
    }
    localStorage.setItem(chaveRascunho(), JSON.stringify(atual));
  }

  // Ao voltar à página (reload/queda), reenvia o rascunho pendente e restaura a tela.
  (function restaurarRascunho() {
    var pendente = lerRascunho();
    var chaves = Object.keys(pendente);
    if (!chaves.length) { return; }
    chaves.forEach(function (pid) {
      var radio = form.querySelector('input[name="p_' + pid + '"][value="' + pendente[pid] + '"]');
      if (radio && !form.querySelector('input[name="p_' + pid + '"]:checked')) {
        radio.checked = true;
        marcarGrade(pid, { respondida: 1 });
      }
    });
    enviar({ respostas: pendente });
  })();

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

  document.querySelectorAll('#execucao input[type="radio"]').forEach(function (radio) {
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
      var respondidas = document.querySelectorAll('#execucao input[type="radio"]:checked').length;
      var total = document.querySelectorAll('#execucao input[type="radio"]').length;
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
