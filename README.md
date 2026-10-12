# Yomi Extensions

Patch temporário de duas extensões do [keiyoushi](https://github.com/keiyoushi/extensions-source),
a **Mango Toons** e a **Lycan Toons**, publicadas aqui com o sufixo **(MY)**. Não é um catálogo:
todo o resto continua vindo do keiyoushi, que fica cadastrado nos apps. Quando as correções
entrarem nos projetos de origem, este repo é apagado (veja [Quando apagar](#quando-apagar)).

## Por que existe

- **Lycan Toons:** no Suwayomi, detalhes e capítulos falham com `JsonDecodingException`
  ("Expected quotation mark… had '<'"). O `evaluateJavaScript` do WebView do Suwayomi (KCEF)
  devolve o resultado cru, e o Android devolve uma string JSON entre aspas. O keiyoushi não vai
  contornar isso na extensão ([Suwayomi #2313](https://github.com/Suwayomi/Suwayomi-Server/issues/2313)).
  A (MY) aceita os dois formatos. No celular a Lycan do keiyoushi já funciona.
- **Mango Toons:** o site migrou a API para `/api/v1` e a extensão do keiyoushi ainda chama as
  rotas antigas, que dão 404. A (MY) usa a API nova.

| Extensão | pkg | ID de fonte (o mesmo do keiyoushi) |
|---|---|---|
| Lycan Toons (MY) | `eu.kanade.tachiyomi.extension.pt.lycantoonsmy` | `9117178890425713139` |
| Mango Toons (MY) | `eu.kanade.tachiyomi.extension.pt.mangotoonsmy` | `8989984812354857153` |

O ID de fonte é o mesmo da original, então as obras da biblioteca continuam abrindo depois da
troca, nos dois sentidos. Pelo mesmo motivo, a original e a (MY) não podem ficar instaladas
juntas.

## O que tem aqui

- `upstream-commit.txt`: o commit do `keiyoushi/extensions-source` sobre o qual os patches valem.
- `patches/<lang>.<módulo>.patch`: um patch por extensão, aplicado em `src/<lang>/<módulo>`.
  Cada patch muda o nome (sufixo "(MY)"), o `pkgName` (sufixo `my`), fixa o `id` da fonte e
  corrige o defeito. A Mango (MY) deixa de usar o tema `mangotheme` (que a Sagrado Império da
  Britannia e a Bladetoons ainda usam com a API antiga) e fala direto com a
  `https://api.mangotoons.com/api/v1`, sem login e sem filtros.
- `.github/workflows/publish.yml`: o workflow que builda, assina e publica.
- `scripts/publish.py`: gera a Release, o `index.pb` e o `repo.json` (adaptado do
  `publish-repo.py` do keiyoushi).
- `scripts/acceptance.py`: o teste de aceite contra o Suwayomi local.

O repo não guarda uma cópia do keiyoushi: o workflow faz checkout do upstream no commit fixado,
aplica os patches, carrega só os módulos patcheados (mais `core`, `compiler`, `common`, `lib` e
`lib-multisrc`) e builda.

## Buildar e publicar

1. Actions → **Publish** → **Run workflow** (só roda à mão, não há build agendado).
2. O workflow:
   - falha logo de cara se faltar um dos secrets `SIGNING_KEY`, `ALIAS`, `KEY_STORE_PASSWORD` ou
     `KEY_PASSWORD`, para nunca publicar algo assinado com a chave de debug;
   - numera a publicação pela última Release mais um (o repo foi recriado depois da `v3`, então a contagem recomeça na `v4`) e usa esse número como
     `versionCode` (a `v7` publica a versão `1.6.7`), então cada publicação sobe a versão e os apps
     oferecem a atualização; uma execução que falha não gasta número;
   - confere que cada APK e JAR saiu assinado com o keystore;
   - cria a Release `v<número>` com o APK e o JAR de cada extensão;
   - grava `index.pb`, `index.json` e `repo.json` no branch `repo`.

O keystore está numa entrada do Bitwarden (JKS e senhas). `SIGNING_KEY` é o JKS em base64. Se
o keystore se perder, gere outro e atualize os secrets: cada extensão vai precisar ser
reinstalada, mas a biblioteca não se perde.

### Atualizar o upstream ou um patch

Se o site mudar de novo, ou o commit fixado ficar incompatível com o Komikku ou o Suwayomi:

```sh
git clone https://github.com/keiyoushi/extensions-source && cd extensions-source
git checkout <commit novo>              # ou o de upstream-commit.txt, para só mexer no patch
git apply ../yomi-extensions/patches/pt.lycantoons.patch   # resolva se não aplicar
# edite src/pt/lycantoons/...
git diff -- src/pt/lycantoons > ../yomi-extensions/patches/pt.lycantoons.patch
```

Grave o commit novo em `upstream-commit.txt`, faça push e rode o workflow.

## Endereço do repo nos apps

- Suwayomi: `https://raw.githubusercontent.com/imonteiroyz/yomi-extensions/repo/index.pb`
- Komikku: `https://raw.githubusercontent.com/imonteiroyz/yomi-extensions/repo/repo.json`

## Trocar as extensões

A original e a (MY) têm o mesmo ID de fonte: sempre desinstale uma antes de instalar a outra.
A biblioteca se mantém.

- **Suwayomi:** repos `yomi-extensions` e keiyoushi cadastrados. Mango e Lycan do keiyoushi
  desinstaladas, as duas (MY) instaladas. As páginas e imagens da Lycan ficam atrás de um
  desafio do Cloudflare, que o Suwayomi só passa com o FlareSolverr ligado (`localhost:8191`,
  "flareSolverrEnabled" nas configurações). Sem ele, as imagens dão erro 500
  "Cloudflare bypass currently disabled".
- **Komikku:** repo `yomi-extensions` cadastrado. Só a Mango é trocada pela (MY); a Lycan do
  keiyoushi funciona no Android.

Depois de trocar, rode o aceite (precisa de um título que a busca encontre):

```sh
python scripts/acceptance.py eu.kanade.tachiyomi.extension.pt.lycantoonsmy "O Rei Supremo de Sichuan"
python scripts/acceptance.py eu.kanade.tachiyomi.extension.pt.mangotoonsmy "Cavaleiro em Eterna Regressão" \
    --library /obra/11132 --library /obra/13480 --library /obra/12090
```

Ele confere que a extensão vem do `yomi-extensions`, instala ou atualiza se preciso, e testa
popular, recentes, busca, detalhes, capítulos, páginas e o download da primeira imagem. Use na
busca uma obra que não esteja na biblioteca, porque a busca atualiza a lista de capítulos dela. Cada
`--library` abre uma obra que já está na biblioteca pelo endereço salvo (detalhes, páginas e
imagem do capítulo mais novo), sem atualizar a lista de capítulos: atualizar apaga da biblioteca
os capítulos que o site tirou do ar.

## Quando apagar

- **Mango:** quando o [keiyoushi #19894](https://github.com/keiyoushi/extensions-source/pull/19894)
  entrar e sair numa versão, desinstale a (MY) e instale a original. Na versão do keiyoushi, abrir
  uma obra também atualiza a lista de capítulos (regra do projeto), então capítulos que o site
  apagou somem da biblioteca já nesse momento.
- **Lycan:** quando o Suwayomi publicar uma versão com o
  [Suwayomi #2428](https://github.com/Suwayomi/Suwayomi-Server/pull/2428), atualize o Suwayomi,
  desinstale a (MY) e instale a do keiyoushi. No celular nada muda.
- Com as duas de volta: remova o repo dos apps e arquive ou apague o `yomi-extensions`.
