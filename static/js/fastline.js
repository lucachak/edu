/* FastLine — comportamento da interface.
 * Tudo aqui é melhoria progressiva: os formulários funcionam sem JavaScript.
 * Nenhuma credencial ou regra de preço fica no navegador. */
(function () {
  "use strict";

  const $ = (sel, raiz) => (raiz || document).querySelector(sel);
  const $$ = (sel, raiz) => Array.from((raiz || document).querySelectorAll(sel));

  function csrf() {
    const campo = $("input[name=csrfmiddlewaretoken]");
    return campo ? campo.value : "";
  }


  // ------------------------------------------------------- animações / ajudantes
  function reanimar(el, classe) {
    el.classList.remove(classe);
    void el.offsetWidth; // força o navegador a reiniciar a animação
    el.classList.add(classe);
    el.addEventListener("animationend", () => el.classList.remove(classe), { once: true });
  }

  function confirmarBotao(botao) {
    if (botao.dataset.rotuloOriginal) return;
    botao.dataset.rotuloOriginal = botao.textContent;
    botao.classList.add("adicionado");
    botao.textContent = "Adicionado \u2713";
    setTimeout(() => {
      botao.textContent = botao.dataset.rotuloOriginal;
      botao.classList.remove("adicionado");
      delete botao.dataset.rotuloOriginal;
    }, 1500);
  }

  // Ondinha suave ao tocar nos botões principais.
  document.addEventListener("pointerdown", (ev) => {
    const btn = ev.target.closest && ev.target.closest(".btn-primario, .btn-secundario, .btn-escuro, .btn-sucesso");
    if (!btn || btn.classList.contains("btn-carrinho") || btn.disabled) return;
    const caixa = btn.getBoundingClientRect();
    const tamanho = Math.max(caixa.width, caixa.height) * 1.6;
    const onda = document.createElement("span");
    onda.className = "onda";
    onda.style.cssText = "width:" + tamanho + "px;height:" + tamanho + "px;left:" + (ev.clientX - caixa.left - tamanho / 2) + "px;top:" + (ev.clientY - caixa.top - tamanho / 2) + "px";
    btn.appendChild(onda);
    onda.addEventListener("animationend", () => onda.remove());
  }, { passive: true });

  // Saudação conforme a hora do dia.
  $$("[data-saudacao]").forEach((el) => {
    const h = new Date().getHours();
    const momento = h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
    const dica = h < 12 ? "Que tal garantir o lanche do intervalo?" : h < 18 ? "Já pensou no que vai pedir hoje?" : "Deixe o pedido de amanhã adiantado.";
    const nome = (el.dataset.nome || "").trim();
    el.textContent = momento + (nome ? ", " + nome : "") + "! " + dica;
  });

  // Entrada escalonada dos cartões (também em listas montadas depois do carregamento).
  $$(".grade-produtos .produto, .lista-cantinas .cantina").forEach((el, i) => el.style.setProperty("--i", String(Math.min(i, 12))));

  // ---------------------------------------------------------------- mensagens
  function mostrarMensagem(texto, tipo) {
    if (!texto) return;
    let caixa = $(".mensagens");
    if (!caixa) {
      caixa = document.createElement("div");
      caixa.className = "mensagens";
      caixa.setAttribute("aria-live", "polite");
      document.body.appendChild(caixa);
    }
    const alerta = document.createElement("div");
    alerta.className = "alerta alerta-" + (tipo || "info");
    alerta.setAttribute("role", tipo === "error" ? "alert" : "status");
    const span = document.createElement("span");
    span.textContent = texto;
    const fechar = document.createElement("button");
    fechar.type = "button";
    fechar.setAttribute("aria-label", "Fechar");
    fechar.textContent = "×";
    alerta.append(span, fechar);
    caixa.appendChild(alerta);
    agendarRemocao(alerta);
  }

  function removerAlerta(alerta) {
    if (!alerta || !alerta.isConnected || alerta.classList.contains("saindo")) return;
    alerta.classList.add("saindo");
    setTimeout(() => alerta.remove(), 260);
  }

  function agendarRemocao(alerta) {
    const tempo = alerta.classList.contains("alerta-error") ? 9000 : 5000;
    alerta.style.setProperty("--duracao-alerta", tempo + "ms");
    setTimeout(() => removerAlerta(alerta), tempo);
  }

  document.addEventListener("click", (ev) => {
    const botao = ev.target.closest(".alerta button");
    if (botao) removerAlerta(botao.closest(".alerta"));
  });
  $$(".mensagens .alerta").forEach(agendarRemocao);

  // ------------------------------------------------- confirmação de ações
  function confirmar(mensagem, titulo) {
    return new Promise((resolve) => {
      const fundo = document.createElement("div");
      fundo.className = "modal-fundo";
      fundo.innerHTML =
        '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-titulo">' +
        '<h2 id="modal-titulo"></h2><p></p>' +
        '<div class="modal-acoes">' +
        '<button type="button" class="sim" aria-label="Confirmar"><svg class="icone" viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg></button>' +
        '<button type="button" class="nao" aria-label="Cancelar"><svg class="icone" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/></svg></button>' +
        "</div></div>";
      $("h2", fundo).textContent = titulo || "Tudo certo?";
      $("p", fundo).textContent = mensagem;
      document.body.appendChild(fundo);
      const fechar = (valor) => { fundo.remove(); document.removeEventListener("keydown", tecla); resolve(valor); };
      const tecla = (e) => { if (e.key === "Escape") fechar(false); };
      document.addEventListener("keydown", tecla);
      $(".sim", fundo).addEventListener("click", () => fechar(true));
      $(".nao", fundo).addEventListener("click", () => fechar(false));
      fundo.addEventListener("click", (e) => { if (e.target === fundo) fechar(false); });
      $(".sim", fundo).focus();
    });
  }

  // Formulários com data-confirmar pedem confirmação antes de enviar.
  document.addEventListener("submit", async (ev) => {
    const form = ev.target;
    if (form.dataset.confirmar && !form.dataset.confirmado) {
      ev.preventDefault();
      const ok = await confirmar(form.dataset.confirmar, form.dataset.confirmarTitulo);
      if (ok) {
        form.dataset.confirmado = "1";
        const botao = ev.submitter || $("[type=submit]", form);
        if (botao && botao.name) {
          const oculto = document.createElement("input");
          oculto.type = "hidden"; oculto.name = botao.name; oculto.value = botao.value;
          form.appendChild(oculto);
        }
        if (botao) botao.classList.add("carregando");
        form.submit();
      }
      return;
    }
    if (form.dataset.ajax !== undefined) return; // tratado abaixo
    const botao = ev.submitter || $("[type=submit]", form);
    if (botao && !form.hasAttribute("data-sem-carregando")) {
      setTimeout(() => { botao.classList.add("carregando"); botao.setAttribute("aria-busy", "true"); }, 0);
    }
  }, true);

  // ------------------------------------------------------------ carrinho
  const gaveta = $("#gaveta-carrinho");

  function abrirCarrinho() {
    if (!gaveta) return;
    document.body.classList.add("gaveta-aberta");
    gaveta.setAttribute("aria-hidden", "false");
    const fechar = $(".gaveta-topo button", gaveta);
    if (fechar) fechar.focus();
  }
  function fecharCarrinho() {
    document.body.classList.remove("gaveta-aberta");
    if (gaveta) gaveta.setAttribute("aria-hidden", "true");
  }

  document.addEventListener("click", (ev) => {
    if (ev.target.closest("[data-abrir-carrinho]")) { ev.preventDefault(); abrirCarrinho(); }
    if (ev.target.closest("[data-fechar-carrinho]")) { ev.preventDefault(); fecharCarrinho(); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharCarrinho(); });

  function atualizarContadores(qtd) {
    $$("[data-contador-carrinho]").forEach((el) => {
      const mudou = el.textContent.trim() !== String(qtd);
      el.textContent = qtd;
      el.hidden = !qtd;
      if (mudou && qtd) reanimar(el, "pulo");
    });
  }

  async function enviarAjax(form, botao) {
    if (botao) botao.classList.add("carregando");
    try {
      const resposta = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf(), Accept: "application/json" },
        credentials: "same-origin",
      });
      if (resposta.redirected || !(resposta.headers.get("content-type") || "").includes("json")) {
        window.location.href = resposta.url; // sessão expirada, etc.
        return;
      }
      const dados = await resposta.json();
      if ($("[data-pagina-carrinho]")) { window.location.reload(); return; }
      if (dados.html !== undefined) {
        const corpo = $("#carrinho-conteudo");
        if (corpo) corpo.innerHTML = dados.html;
      }
      atualizarContadores(dados.quantidade || 0);
      const abre = form.dataset.abrirDepois !== undefined && dados.ok;
      if (dados.ok && botao && form.dataset.abrirDepois !== undefined) confirmarBotao(botao);
      // Ao abrir o carrinho, a própria gaveta já mostra o item adicionado.
      if (dados.mensagem && !abre) mostrarMensagem(dados.mensagem, dados.ok ? "success" : "error");
      if (abre) abrirCarrinho();
    } catch (erro) {
      mostrarMensagem("Não foi possível falar com o servidor. Verifique sua conexão.", "error");
    } finally {
      if (botao) botao.classList.remove("carregando");
    }
  }

  document.addEventListener("submit", (ev) => {
    const form = ev.target;
    if (form.dataset.ajax === undefined || !window.fetch) return;
    ev.preventDefault();
    enviarAjax(form, ev.submitter || $("[type=submit]", form));
  });

  // ------------------------------------------------- filtro de categorias
  $$("[data-filtro-categoria]").forEach((chip) => {
    chip.addEventListener("click", (ev) => {
      ev.preventDefault();
      const alvo = chip.dataset.filtroCategoria;
      $$("[data-filtro-categoria]").forEach((c) => {
        c.classList.toggle("ativo", c === chip);
        c.setAttribute("aria-pressed", c === chip ? "true" : "false");
      });
      let visiveis = 0;
      $$("[data-categoria]").forEach((card) => {
        const mostrar = alvo === "todos" || card.dataset.categoria === alvo;
        const estavaOculto = card.hidden;
        card.hidden = !mostrar;
        if (mostrar) {
          card.style.setProperty("--i", String(Math.min(visiveis, 12)));
          if (estavaOculto || alvo !== "todos") reanimar(card, "entrando");
          visiveis += 1;
        }
      });
      const vazio = $("#cardapio-filtro-vazio");
      if (vazio) vazio.hidden = visiveis > 0;
    });
  });

  // --------------------------------------------------------- PIX / status
  const aguardando = $("[data-status-url]");
  if (aguardando) {
    let tentativas = 0;
    const consultar = async () => {
      tentativas += 1;
      try {
        const r = await fetch(aguardando.dataset.statusUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" });
        if (r.ok) {
          const dados = await r.json();
          if (dados.confirmado) { window.location.href = dados.url; return; }
          if (dados.status === "cancelado") { window.location.reload(); return; }
        }
      } catch (e) { /* tenta de novo */ }
      if (tentativas < 120) setTimeout(consultar, tentativas < 10 ? 4000 : 8000);
    };
    setTimeout(consultar, 4000);
  }

  $$("[data-copiar]").forEach((botao) => {
    botao.addEventListener("click", async () => {
      const campo = document.getElementById(botao.dataset.copiar);
      if (!campo) return;
      try {
        await navigator.clipboard.writeText(campo.value);
      } catch (e) {
        campo.select();
        document.execCommand("copy");
      }
      mostrarMensagem("Código PIX copiado!", "success");
    });
  });

  // Copia um texto fixo (ex.: código da cantina no painel).
  $$("[data-copiar-texto]").forEach((botao) => {
    botao.addEventListener("click", async () => {
      const texto = botao.dataset.copiarTexto;
      try {
        await navigator.clipboard.writeText(texto);
      } catch (e) {
        const temp = document.createElement("textarea");
        temp.value = texto;
        document.body.appendChild(temp);
        temp.select();
        document.execCommand("copy");
        document.body.removeChild(temp);
      }
      mostrarMensagem(botao.dataset.copiado || "Copiado!", "success");
    });
  });



  const nascimentoCadastro = $('input[name="data_nascimento"]');
  const blocoResponsavel = $("[data-responsavel-container]");
  const emailResponsavel = $('input[name="email_responsavel"]');
  function atualizarCampoResponsavel() {
    if (!nascimentoCadastro || !blocoResponsavel || !nascimentoCadastro.value) return;
    const nascimento = new Date(nascimentoCadastro.value + "T12:00:00");
    const hoje = new Date();
    let idade = hoje.getFullYear() - nascimento.getFullYear();
    if (hoje.getMonth() < nascimento.getMonth() || (hoje.getMonth() === nascimento.getMonth() && hoje.getDate() < nascimento.getDate())) idade--;
    const precisa = idade < 17;
    blocoResponsavel.hidden = !precisa;
    if (emailResponsavel) emailResponsavel.required = precisa;
  }
  if (nascimentoCadastro) {
    nascimentoCadastro.addEventListener("change", atualizarCampoResponsavel);
    atualizarCampoResponsavel();
  }

  // (A troca Cliente/Cantina da tela de login agora é feita pelo script da própria
  // página usuarios/login.html, para não depender deste arquivo nem do cache.)

  // --------------------------------------------------------- carrossel do cardápio
  $$(".fastline-food-carousel").forEach((carousel) => {
    const slides = $$(".food-slide", carousel);
    const shell = carousel.closest(".food-carousel-shell") || carousel;
    const dotsContainer = $(".food-dots", shell);
    if (!slides.length || !dotsContainer) return;

    let atual = 0;
    let timer = null;
    let ponteiroSobre = false;
    let focoInterno = false;
    const movimentoReduzido = window.matchMedia("(prefers-reduced-motion: reduce)");

    carousel.setAttribute("aria-roledescription", "carrossel");
    carousel.setAttribute("tabindex", "0");
    slides.forEach((slide, i) => {
      slide.setAttribute("role", "group");
      slide.setAttribute("aria-roledescription", "slide");
      slide.setAttribute("aria-label", `${i + 1} de ${slides.length}`);
    });

    const anterior = document.createElement("button");
    anterior.type = "button";
    anterior.className = "food-nav food-nav-anterior";
    anterior.setAttribute("aria-label", "Destaque anterior");
    anterior.textContent = "‹";

    const proximo = document.createElement("button");
    proximo.type = "button";
    proximo.className = "food-nav food-nav-proximo";
    proximo.setAttribute("aria-label", "Próximo destaque");
    proximo.textContent = "›";

    shell.append(anterior, proximo);

    const atualizar = (indice, rolar = true) => {
      atual = (indice + slides.length) % slides.length;
      if (rolar) {
        const destino = slides[atual].offsetLeft - slides[0].offsetLeft;
        carousel.scrollTo({ left: destino, behavior: movimentoReduzido.matches ? "auto" : "smooth" });
      }
      slides.forEach((slide, i) => slide.classList.toggle("ativo", i === atual));
      $$(".food-dot", dotsContainer).forEach((dot, i) => {
        const ativo = i === atual;
        dot.classList.toggle("ativo", ativo);
        dot.setAttribute("aria-current", ativo ? "true" : "false");
      });
    };

    slides.forEach((slide, i) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "food-dot";
      dot.setAttribute("aria-label", `Mostrar destaque ${i + 1}`);
      dot.setAttribute("aria-current", i === 0 ? "true" : "false");
      dot.addEventListener("click", () => { atualizar(i); reiniciar(); });
      dotsContainer.appendChild(dot);
    });

    anterior.addEventListener("click", () => { atualizar(atual - 1); reiniciar(); });
    proximo.addEventListener("click", () => { atualizar(atual + 1); reiniciar(); });

    const pausar = () => { if (timer) window.clearInterval(timer); timer = null; };
    const iniciar = () => {
      pausar();
      if (slides.length < 2 || movimentoReduzido.matches || document.hidden || ponteiroSobre || focoInterno) return;
      timer = window.setInterval(() => atualizar(atual + 1), 5000);
    };
    const reiniciar = () => iniciar();

    if ("IntersectionObserver" in window) {
      const observador = new IntersectionObserver((entradas) => {
        const visiveis = entradas.filter((entrada) => entrada.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visiveis.length) {
          const indice = slides.indexOf(visiveis[0].target);
          if (indice >= 0) atualizar(indice, false);
        }
      }, { root: carousel, threshold: [0.55, 0.7, 0.9] });
      slides.forEach((slide) => observador.observe(slide));
    }

    carousel.addEventListener("mouseenter", () => { ponteiroSobre = true; pausar(); });
    carousel.addEventListener("mouseleave", () => { ponteiroSobre = false; iniciar(); });
    carousel.addEventListener("focusin", () => { focoInterno = true; pausar(); });
    carousel.addEventListener("focusout", (ev) => {
      if (!carousel.contains(ev.relatedTarget)) { focoInterno = false; iniciar(); }
    });
    document.addEventListener("visibilitychange", () => document.hidden ? pausar() : iniciar());
    movimentoReduzido.addEventListener?.("change", iniciar);
    carousel.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowRight") { ev.preventDefault(); atualizar(atual + 1); reiniciar(); }
      if (ev.key === "ArrowLeft") { ev.preventDefault(); atualizar(atual - 1); reiniciar(); }
    });

    atualizar(0, false);
    iniciar();
  });

  document.querySelectorAll("[data-reveal]").forEach((el) => {
    if (!("IntersectionObserver" in window)) { el.classList.add("visivel"); return; }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visivel");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    observer.observe(el);
  });

  // ------------------------------------------------------------- outros
  $$("[data-maiusculo]").forEach((campo) => {
    campo.addEventListener("input", () => {
      const pos = campo.selectionStart;
      campo.value = campo.value.toUpperCase();
      campo.setSelectionRange(pos, pos);
    });
  });

  // Mostra o tempo restante da reserva.
  $$("[data-expira-em]").forEach((el) => {
    const fim = new Date(el.dataset.expiraEm).getTime();
    const tick = () => {
      const resto = Math.max(0, Math.round((fim - Date.now()) / 1000));
      const m = String(Math.floor(resto / 60)).padStart(2, "0");
      const s = String(resto % 60).padStart(2, "0");
      el.textContent = m + ":" + s;
      if (resto > 0) setTimeout(tick, 1000);
      else window.location.reload();
    };
    tick();
  });
})();

