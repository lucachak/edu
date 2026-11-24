from django.urls import reverse

from estabelecimentos.models import estabelecimento as Estabelecimento
from usuarios.models import Permissao, Usuario

from .base import SENHA, FastLineTestCase


class CadastroEAutenticacaoTests(FastLineTestCase):
    def test_cadastro_cria_cliente_com_senha_em_hash(self):
        resp = self.client.post(reverse("usuarios:cadastro"), {
            "nome": "Maria Nova", "email": "Maria@Teste.com", "data_nascimento": "2001-02-03",
            "senha": "Batata-Doce-77", "confirmar_senha": "Batata-Doce-77",
        })
        self.assertRedirects(resp, reverse("estabelecimentos:escolher"))
        usuario = Usuario.objects.get(email="maria@teste.com")
        self.assertEqual(usuario.permissao, Permissao.CLIENTE)
        self.assertNotEqual(usuario.password, "Batata-Doce-77")
        self.assertTrue(usuario.password.startswith(("pbkdf2_", "argon2", "scrypt")))
        self.assertTrue(usuario.check_password("Batata-Doce-77"))

    def test_cadastro_nao_permite_escolher_permissao(self):
        self.client.post(reverse("usuarios:cadastro"), {
            "nome": "Hacker", "email": "h@teste.com", "data_nascimento": "2001-02-03",
            "senha": "Batata-Doce-77", "confirmar_senha": "Batata-Doce-77", "permissao": "admin",
        })
        self.assertEqual(Usuario.objects.get(email="h@teste.com").permissao, Permissao.CLIENTE)

    def test_cadastro_valida_senhas_e_email_duplicado(self):
        resp = self.client.post(reverse("usuarios:cadastro"), {
            "nome": "X", "email": "cliente@teste.com", "data_nascimento": "2001-02-03",
            "senha": "123", "confirmar_senha": "456",
        })
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertIn("email", form.errors)
        self.assertIn("confirmar_senha", form.errors)

    def test_login_e_logout(self):
        resp = self.client.post(reverse("usuarios:login"), {"area": "cliente", "email": "cliente@teste.com", "senha": SENHA})
        self.assertRedirects(resp, reverse("produtos:cardapio"))
        resp = self.client.post(reverse("usuarios:logout"))
        self.assertRedirects(resp, reverse("usuarios:login"))
        self.assertEqual(self.client.get(reverse("produtos:cardapio")).status_code, 302)

    def test_login_senha_errada(self):
        resp = self.client.post(reverse("usuarios:login"), {"area": "cliente", "email": "cliente@teste.com", "senha": "errada"})
        self.assertContains(resp, "E-mail ou senha inválidos")

    def test_logout_exige_post(self):
        self.entrar(self.cliente)
        self.assertEqual(self.client.get(reverse("usuarios:logout")).status_code, 405)

    def test_funcionario_entra_pela_area_cantina(self):
        resp = self.client.post(reverse("usuarios:login"), {"area": "cantina", "email": "func.a@teste.com", "senha": SENHA})
        self.assertRedirects(resp, reverse("painel:pedidos"))

    def test_editar_dados_pessoais(self):
        self.entrar(self.outro_cliente)
        resp = self.client.post(reverse("usuarios:perfil"), {
            "nome": "Cliente Editado", "email": "outro@teste.com", "data_nascimento": "1999-01-01",
            "cpf": "529.982.247-25", "telefone": "(11) 91234-5678",
        })
        self.assertRedirects(resp, reverse("usuarios:perfil"))
        self.outro_cliente.refresh_from_db()
        self.assertEqual(self.outro_cliente.nome, "Cliente Editado")
        self.assertEqual(self.outro_cliente.cpf, "")

    def test_perfil_nao_coleta_cpf_ou_telefone(self):
        self.entrar(self.outro_cliente)
        resp = self.client.get(reverse("usuarios:perfil"))
        self.assertNotIn("cpf", resp.context["form"].fields)
        self.assertNotIn("telefone", resp.context["form"].fields)

    def test_funcionario_novo_precisa_de_aprovacao_do_gerente(self):
        resp = self.client.post(reverse("usuarios:cadastro_funcionario"), {
            "nome": "Funcionário Novo", "email": "novo@teste.com",
            "senha": "Senha-Forte-987", "confirmar_senha": "Senha-Forte-987",
            "codigo_convite": "FASTLINE-DEMO-2026",
        })
        self.assertRedirects(resp, reverse("usuarios:login"))
        novo = Usuario.objects.get(email="novo@teste.com")
        self.assertFalse(novo.estabelecimentos_vinculados().exists())
        self.client.post(reverse("usuarios:login"), {
            "area": "cantina", "email": "gerente@fastline.demo", "senha": "FastLineDemo2026!",
        })
        vinculo = novo.vinculos.get()
        resp = self.client.post(reverse("painel:aprovar_funcionario", args=[vinculo.pk]))
        self.assertRedirects(resp, reverse("painel:funcionarios"))
        self.assertTrue(novo.estabelecimentos_vinculados().exists())


class PermissoesTests(FastLineTestCase):
    def test_anonimo_redirecionado_para_login(self):
        for nome in ("produtos:cardapio", "pedidos:tickets", "painel:pedidos", "administracao:painel"):
            resp = self.client.get(reverse(nome))
            self.assertEqual(resp.status_code, 302, nome)
            self.assertIn(reverse("usuarios:login"), resp["Location"])

    def test_cliente_nao_acessa_painel_nem_administracao(self):
        self.entrar(self.cliente)
        self.assertEqual(self.client.get(reverse("painel:pedidos")).status_code, 403)
        self.assertEqual(self.client.get(reverse("painel:itens")).status_code, 403)
        self.assertEqual(self.client.get(reverse("administracao:painel")).status_code, 403)
        self.assertEqual(self.client.post(reverse("administracao:estabelecimento_novo"), {"nome": "X"}).status_code, 403)

    def test_funcionario_nao_acessa_administracao_nem_area_do_cliente(self):
        self.entrar(self.func_a)
        self.assertEqual(self.client.get(reverse("administracao:estabelecimentos")).status_code, 403)
        self.assertEqual(self.client.get(reverse("produtos:cardapio")).status_code, 403)

    def test_funcionario_sem_vinculo_ativo_bloqueado(self):
        self.func_a.vinculos.update(ativo=False)
        self.entrar(self.func_a)
        self.assertEqual(self.client.get(reverse("painel:pedidos")).status_code, 403)

    def test_vinculo_sem_gerenciar_produtos(self):
        self.func_a.vinculos.update(pode_gerenciar_produtos=False)
        self.entrar(self.func_a)
        resp = self.client.get(reverse("painel:produto_editar", args=[self.coxinha.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_admin_acessa_tudo_da_administracao(self):
        self.entrar(self.admin)
        for nome in ("administracao:painel", "administracao:estabelecimentos", "administracao:usuarios"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)

    def test_pagina_403_personalizada(self):
        self.entrar(self.cliente)
        resp = self.client.get(reverse("administracao:painel"))
        self.assertContains(resp, "Acesso negado", status_code=403)


class EstabelecimentosTests(FastLineTestCase):
    def test_somente_admin_cadastra_estabelecimento(self):
        dados = {"nome": "Cantina Nova", "endereco": "Rua 3", "ativo": "on"}
        self.entrar(self.func_a)
        self.client.post(reverse("administracao:estabelecimento_novo"), dados)
        self.assertFalse(Estabelecimento.objects.filter(nome="Cantina Nova").exists())
        self.entrar(self.admin)
        resp = self.client.post(reverse("administracao:estabelecimento_novo"), dados)
        self.assertRedirects(resp, reverse("administracao:estabelecimentos"))
        self.assertTrue(Estabelecimento.objects.filter(nome="Cantina Nova", ativo=True).exists())

    def test_admin_edita_e_desativa(self):
        self.entrar(self.admin)
        url = reverse("administracao:estabelecimento_editar", args=[self.cantina_b.unique_id])
        self.client.post(url, {"nome": "Cantina B2", "endereco": "Rua 2", "ativo": "on"})
        self.cantina_b.refresh_from_db()
        self.assertEqual(self.cantina_b.nome, "Cantina B2")
        self.client.post(reverse("administracao:estabelecimento_ativo", args=[self.cantina_b.unique_id]))
        self.cantina_b.refresh_from_db()
        self.assertFalse(self.cantina_b.ativo)

    def test_cliente_nao_ve_estabelecimento_desativado(self):
        self.cantina_b.ativo = False
        self.cantina_b.save()
        self.entrar(self.cliente)
        resp = self.client.get(reverse("estabelecimentos:escolher"))
        self.assertNotContains(resp, "Cantina B")
        resp = self.client.post(reverse("estabelecimentos:selecionar", args=[self.cantina_b.unique_id]))
        self.assertEqual(resp.status_code, 404)

    def test_cliente_seleciona_e_favorita(self):
        self.entrar(self.outro_cliente)
        self.client.post(reverse("estabelecimentos:selecionar", args=[self.cantina_b.unique_id]))
        self.outro_cliente.refresh_from_db()
        self.assertEqual(self.outro_cliente.estabelecimento_atual, self.cantina_b)
        # Conectar-se à cantina já a salva na conta; o botão alterna (remove/salva).
        self.assertIn(self.cantina_b, self.outro_cliente.favoritos.all())
        self.client.post(reverse("estabelecimentos:favorito", args=[self.cantina_b.unique_id]))
        self.assertNotIn(self.cantina_b, self.outro_cliente.favoritos.all())
        self.client.post(reverse("estabelecimentos:favorito", args=[self.cantina_b.unique_id]))
        self.assertIn(self.cantina_b, self.outro_cliente.favoritos.all())

    def test_admin_gerencia_permissoes_e_vinculos(self):
        self.entrar(self.admin)
        url = reverse("administracao:vinculo_adicionar", args=[self.outro_cliente.pk])
        self.client.post(url, {"estabelecimento": self.cantina_b.pk, "funcao": "Caixa", "ativo": "on"})
        self.outro_cliente.refresh_from_db()
        self.assertEqual(self.outro_cliente.permissao, Permissao.FUNCIONARIO)
        self.assertTrue(self.outro_cliente.vinculos.filter(estabelecimento=self.cantina_b).exists())

    def test_admin_nao_remove_o_proprio_acesso(self):
        self.entrar(self.admin)
        resp = self.client.post(reverse("administracao:usuario_editar", args=[self.admin.pk]), {
            "nome": "Admin", "email": "admin@teste.com", "permissao": "cliente", "is_active": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.permissao, Permissao.ADMIN)
