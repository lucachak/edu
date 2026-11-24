# Guia de uso e manutenção do FastLine

Este documento explica o que foi alterado, como cada parte funciona e como cadastrar uma nova cantina com seu gerente.

## 1. Menu lateral

O menu foi redesenhado para ter uma hierarquia mais clara: marca no topo, navegação no centro, cantina ativa e conta no rodapé. Os estados de seleção, hover e foco usam transições curtas. O menu continua adaptado para celular e respeita a preferência do navegador por movimento reduzido.

Os itens continuam sendo montados pelo `core/context_processors.py`. Para adicionar um novo item de navegação, inclua uma tupla na função de navegação do perfil correto, com identificador, texto, URL e nome do ícone.

## 2. Carrossel do cardápio

O carrossel da tela `templates/produtos/cardapio.html` agora tem rolagem suave, indicadores clicáveis, avanço automático e pausa quando o cursor ou o foco está sobre ele. As imagens ficam em `static/img/produtos/`.

Para trocar uma imagem:
1. Coloque a nova imagem em `static/img/produtos/`.
2. Abra `templates/produtos/cardapio.html`.
3. Localize o slide correspondente e altere o caminho dentro da tag `static`.
4. Atualize o texto alternativo `alt` para descrever a nova imagem.

## 3. Login por perfil

A tela de login mantém uma única área de e-mail e senha. Ao selecionar Cliente, aparecem apenas as opções de cadastro de cliente. Ao selecionar Cantina, aparecem as opções de acesso e solicitação de vínculo de funcionário. Um pequeno script dentro de `templates/usuarios/login.html` altera título, botão e links sem mudar a validação do servidor; ele não depende do `fastline.js`.

A seleção visual não concede permissão. O `LoginForm` e os decoradores em `core/permissions.py` continuam validando o perfil no backend.

## 4. Autorização para clientes com menos de 17 anos

O cadastro solicita a data de nascimento. Para idade inferior a 17 anos, o sistema exige o e-mail de um responsável, cria a conta inativa e envia um link assinado. O link expira em três dias. Quando o responsável confirma, o FastLine ativa a conta e marca a autorização como confirmada.

Os campos ficam no modelo `Usuario`:
- `data_nascimento`
- `email_responsavel`
- `responsavel_confirmado`

A regra é aplicada no formulário de cadastro, na confirmação e no login. Se uma conta antiga pertencer a um menor e ainda não tiver autorização, o cliente informa o e-mail do responsável no login para receber o link. A migração `usuarios.0005_autorizacao_responsavel` adiciona os campos sem apagar contas existentes. Contas existentes com menos de 17 anos e data de nascimento registrada precisam informar o e-mail do responsável no login; as demais contas existentes são preservadas.

### E-mail em desenvolvimento

O backend padrão do projeto é o console. Isso significa que o Django escreve a mensagem e o link no terminal em que `runserver` está rodando. Para envio real, configure SMTP com credenciais guardadas em variáveis de ambiente, defina um remetente e publique o site com HTTPS. Não use o backend de console em produção.

A autorização por link é uma confirmação técnica de e-mail; ela não substitui a avaliação jurídica e os procedimentos de consentimento que a instituição responsável pelo serviço precise adotar.

## 5. Funcionário em mais de uma cantina

Um funcionário continua usando uma única conta. Cada cantina adicional é representada por outro registro `Vinculo`.

Para solicitar uma nova unidade:
1. Entre com a conta de funcionário.
2. No menu lateral, clique em **Adicionar cantina**.
3. Digite o código de convite fornecido pela nova unidade.
4. Aguarde a aprovação de um gerente daquela cantina.
5. Depois da aprovação, use o seletor **Trabalhando em** no menu lateral para alternar entre as unidades.

O backend seleciona o estabelecimento ativo da sessão e filtra as consultas por `request.estabelecimento`. A troca de cantina não muda a senha nem cria outra conta.

## 6. Cliente com várias cantinas

O cliente pode abrir **Cantinas**, consultar os estabelecimentos ativos, favoritar e selecionar outra unidade. Antes de trocar, a página de detalhes mostra nome, endereço, local de retirada, contato e horário informado.

O carrinho é limpo ao trocar de cantina para impedir que itens de uma unidade sejam enviados para outra. Os pedidos antigos permanecem vinculados ao estabelecimento original. Em **Meus Tickets**, o cliente pode filtrar os tickets por cantina.

## 7. Isolamento dos pedidos

Cada pedido guarda a referência do estabelecimento em que foi criado. As telas operacionais usam o vínculo ativo do funcionário e filtram pedidos, vendas, produtos e tokens pela cantina selecionada. O cliente só consulta pedidos associados à própria conta.

Não remova esses filtros ao criar novas telas. Para uma nova consulta do painel, use sempre `request.estabelecimento` como filtro do estabelecimento.

## 8. Criar uma nova cantina com gerente

Esta operação deve ser feita por uma conta com permissão de Administrador da plataforma.

### Etapa A — Cadastrar a cantina

1. Entre na área **Cantina** com a conta de administrador.
2. Abra **Estabelecimentos**.
3. Clique para cadastrar um estabelecimento.
4. Preencha nome, endereço, local de retirada, descrição, e-mail e telefone.
5. Defina um código de convite único. Exemplo: `CANTINA-UNIDADE-02`.
6. Marque a cantina como ativa e salve.

O código de convite deve ser compartilhado apenas com funcionários autorizados daquela unidade.

### Etapa B — Criar a conta do gerente

1. Abra **Usuários** na administração.
2. Crie uma conta com nome, e-mail e senha inicial.
3. Defina a permissão como **Funcionário** e deixe a conta ativa.
4. Salve o usuário.

Se o gerente já tiver uma conta de funcionário, não crie outra. Use a conta existente.

### Etapa C — Vincular o gerente à cantina

1. Abra a edição do usuário gerente.
2. Na área de vínculos, adicione um vínculo.
3. Selecione a nova cantina.
4. Em função, escreva `gerente`.
5. Marque o vínculo como ativo.
6. Marque a opção de gerenciamento de produtos.
7. Salve.

O usuário poderá entrar pela opção **Cantina**. O menu lateral mostrará a unidade vinculada. Se ele gerenciar mais de uma cantina, poderá alternar entre elas.

### Etapa D — Cadastrar produtos

Com o vínculo de gerente ativo:
1. Entre no painel da cantina.
2. Abra **Gerenciar Itens** e cadastre categorias e produtos.
3. Defina a disponibilidade online do dia.
4. Abra **Cardápio do Dia** para publicar o almoço especial.

### Etapa E — Cadastrar funcionários

O gerente pode compartilhar o código de convite com a equipe. O funcionário abre a opção **Solicitar acesso à cantina**, preenche os dados e informa o código. A solicitação aparece em **Aprovar funcionários** para o gerente.

Para funcionários que já usam FastLine em outra unidade, a opção **Adicionar cantina** cria um vínculo pendente na mesma conta.

## 9. Arquivos principais

| Arquivo | Responsabilidade |
|---|---|
| `usuarios/models.py` | Dados da conta, autorização do responsável e vínculos |
| `usuarios/forms.py` | Validação de login, cadastro e solicitação de vínculo |
| `usuarios/views.py` | Login, cadastro, confirmação do responsável e vínculo adicional |
| `estabelecimentos/views.py` | Lista, detalhes e seleção de cantinas |
| `pedidos/views.py` | Tickets do cliente e filtros |
| `painel/views.py` | Operação restrita à cantina ativa |
| `core/context_processors.py` | Itens do menu lateral por perfil |
| `templates/usuarios/login.html` | Tela de login e troca Cliente/Cantina |
| `static/js/fastline.js` | Carrossel, carrinho, animações e demais interações |
| `static/css/fastline.css` | Layout, animações e responsividade |

## 10. Depois de atualizar o projeto

No terminal, na pasta de `manage.py`, execute:

```cmd
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py test
```

Faça uma cópia do `db.sqlite3` antes de atualizar um banco que já tenha dados importantes.
