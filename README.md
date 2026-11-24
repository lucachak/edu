# FastLine

O FastLine é uma plataforma para pedir lanches e refeições antes do intervalo. O cliente escolhe uma cantina, monta o pedido, acompanha o pagamento e recebe um código para retirar sem precisar enfrentar a fila.

O sistema foi feito com Django, Python, SQLite, HTML, CSS e JavaScript. A interface usa tons de marrom, bege e laranja.

## Rodar no Windows

1. Instale o Python 3.13.14.
2. Abra o terminal na pasta que contém `manage.py`.
3. Crie e ative o ambiente virtual:

```cmd
py -3.13 -m venv .venv
.venv\Scripts\activate
```

4. Instale as dependências:

```cmd
python -m pip install -r requirements.txt
```

5. Crie seu `.env` a partir do exemplo:

```cmd
copy .env.example .env
```

6. Aplique as migrações e carregue os dados de demonstração:

```cmd
python manage.py migrate
python manage.py carregar_demo
```

7. Inicie o servidor:

```cmd
python manage.py runserver
```

Abra `http://127.0.0.1:8000`.

## Perfis de acesso

- **Cliente:** escolhe uma ou mais cantinas, consulta cardápios e acompanha seus tickets.
- **Funcionário:** trabalha nas cantinas em que possui vínculo aprovado. Pode alternar entre elas pelo seletor do menu lateral.
- **Gerente da cantina:** é um funcionário com a função `gerente`. Aprova solicitações de acesso àquela cantina.
- **Administrador da plataforma:** cadastra cantinas, cria contas e gerencia vínculos.

## Cadastro de menores de 17 anos

No cadastro de cliente, a data de nascimento é solicitada. Se a pessoa tiver menos de 17 anos, também será solicitado o e-mail de um responsável. A conta fica bloqueada até que o responsável abra o link enviado pelo FastLine.

Em desenvolvimento, o link aparece no terminal porque o projeto usa o backend de e-mail do console. Para enviar mensagens de verdade, configure um serviço SMTP no ambiente e use HTTPS no endereço público.

## Cantinas e tickets

O cliente pode alternar entre cantinas sem perder o histórico de compras. A tela de tickets permite filtrar os pedidos por estabelecimento. Os pedidos continuam associados à cantina em que foram feitos.

Funcionários só consultam pedidos, vendas, produtos e tokens do estabelecimento selecionado. Um vínculo ativo com uma cantina não dá acesso aos dados de outra.

Para trabalhar em outra cantina, o funcionário entra em **Adicionar cantina**, informa o código de convite e aguarda a aprovação de um gerente daquela unidade.

## Criar uma cantina e seu gerente

O passo a passo está em `docs/GUIA_FASTLINE.md`. Em resumo: um administrador cadastra a cantina, cria ou seleciona a conta do gerente e adiciona um vínculo com a função `gerente`.

## Pagamentos

Sem credenciais do PagBank, o FastLine pode operar no modo de pagamento no balcão, confirmado por um funcionário. A integração PagBank deve ser testada em sandbox antes de qualquer uso real. Nunca coloque o token do PagBank no JavaScript ou no repositório.

## Comandos úteis

```cmd
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
```

## Estrutura do projeto

- `usuarios`: contas, autenticação e vínculos.
- `estabelecimentos`: cantinas e seleção do cliente.
- `produtos`: produtos, disponibilidade e cardápio especial.
- `pedidos`: carrinho, pedidos, pagamentos, tickets e retiradas.
- `painel`: operação diária da cantina.
- `administracao`: gestão da plataforma.
- `core`: permissões, navegação e recursos compartilhados.
- `templates`, `static/css` e `static/js`: interface do FastLine.
# edu
