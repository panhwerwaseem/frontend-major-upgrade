# Breaking changes by framework and major

What `scripts/upgrade_scan.py` looks for, and the changes it cannot see. This
file is deliberately incomplete: it lists only changes stated in the official
upgrade guides, and the guide for each major is the full list. Read the guide
for every stage, including stages where the scan finds nothing.

The rule ids below are the ones the scan prints. The patterns and their test
examples are in `scripts/upgrade_rules.py`; `python3 scripts/upgrade_rules.py`
lists them.

## Contents

- [How to read a finding](#how-to-read-a-finding)
- [React](#react)
- [Next.js](#nextjs)
- [Angular](#angular)
- [What the scan does not see](#what-the-scan-does-not-see)

## How to read a finding

| Level | Meaning | What to do |
|---|---|---|
| `break` | The matched API is removed or rejected at that stage | Fix in that stage, codemod first |
| `review` | The pattern cannot decide alone, or a family package is off by a major | Look at the code and record the decision |
| `deprecated` | Deprecated at the target major, removed in a later one | Leave it unless the user wants it; list under "Not done" |

Matching is by regular expression on comment-stripped source. It does not
follow aliases (`import DOM from 'react-dom'` then `DOM.render`), it reports
matches inside string literals, and it cannot tell a class component from a
function component. A string ref is matched only in the usual JSX form
`ref="name"` (no spaces around `=`) or through `this.refs`. Treat every
finding as a pointer to a line to read, and a missing finding as no evidence
either way.

## React

Guides: [React 17](https://legacy.reactjs.org/blog/2020/10/20/react-v17.html),
[React 18](https://react.dev/blog/2022/03/08/react-18-upgrade-guide),
[React 19](https://react.dev/blog/2024/04/25/react-19-upgrade-guide).

### 16 to 17

No rule in the table. The changes are in behaviour: events are delegated to the
root container instead of `document`, event pooling is removed (so
`event.persist()` is no longer needed), and effect cleanup functions run
asynchronously. Code that attaches its own listeners to `document` and relies
on ordering against React handlers is the usual casualty.

### 17 to 18

No rule is `break` at this stage. `ReactDOM.render`, `ReactDOM.hydrate` and
`unmountComponentAtNode` are deprecated in 18 and reported as `deprecated`
when 18 is the target.

- Until the app switches to `createRoot`, it behaves as it did on React 17.
  Switching turns on automatic batching of state updates everywhere, and
  StrictMode starts mounting, unmounting and remounting components in
  development to find unsafe effects.
- Switching to `createRoot` is required by the 19 stage. Whether to do it in
  the 18 stage is the user's call; it is a behaviour change either way.
- Internet Explorer is no longer supported.
- TypeScript: `@types/react` 18 removes the implicit `children` prop, so
  components typed with `React.FC` that accept children need it declared.

### 18 to 19

Move to the latest 18.3 first. It adds warnings for the APIs that 19 removes.

| Rule id | Removed in 19 | Replacement |
|---|---|---|
| `react-dom-render` | `ReactDOM.render` | `createRoot(container).render(element)` from `react-dom/client` |
| `react-dom-hydrate` | `ReactDOM.hydrate` | `hydrateRoot(container, element)` from `react-dom/client` |
| `react-dom-unmount` | `unmountComponentAtNode` | `root.unmount()` |
| `react-find-dom-node` | `findDOMNode` | A ref on the DOM element |
| `react-string-ref` | String refs (`ref="name"`, `this.refs`) | Callback ref, `createRef` or `useRef` |
| `react-legacy-context` | `contextTypes`, `childContextTypes`, `getChildContext` | `createContext` with a Provider and `contextType`, `useContext` or a Consumer |
| `react-create-factory` | `React.createFactory` | JSX or `createElement` |
| `react-render-subtree` | `unstable_renderSubtreeIntoContainer` | `createPortal` |
| `react-test-renderer-shallow` | `react-test-renderer/shallow` | The `react-shallow-renderer` package, or a DOM-rendering test |
| `react-dom-test-utils` (review) | Everything in `react-dom/test-utils` except `act` | `act` from `react`; rewrite tests that used the other helpers |
| `react-function-default-props` (review) | `defaultProps` on function components | Default values in the parameter destructuring. Class components keep `defaultProps` |

Also in 19, with no rule:

- `propTypes` checks are no longer run. Nothing breaks, but the validation
  silently stops.
- The new JSX transform is required.
- The TypeScript types changed (for example `useRef` requires an argument).
  The guide names a types codemod.

## Next.js

Guides: the version guides and the codemods page under
[Upgrading](https://nextjs.org/docs/app/guides/upgrading) in the Next.js
documentation. The guide for version 13 is in the Pages Router documentation.

React moves with Next. Next 13 and 14 need React 18. Next 15 uses React 19
with the App Router and still accepts React 18 with the Pages Router. The scan
attaches React's own rules to the Next stage that brings the new React major.

### 12 to 13

| Rule id | Change in 13 | Replacement |
|---|---|---|
| `next-link-anchor-child` | `next/link` no longer takes an `<a>` child | Remove the `<a>`, or add `legacyBehavior` |
| `next-future-image` | `next/future/image` was renamed | Import `next/image` |
| `next-image-import` (review) | `next/image` is now the component that was `next/future/image`; the old one is `next/legacy/image` | Rename the import to `next/legacy/image` to keep behaviour |

The `app/` directory is optional. Leave `pages/` as it is during the upgrade.

### 13 to 14

| Rule id | Change in 14 | Replacement |
|---|---|---|
| `next-export-script` | The `next export` command is removed | `output: 'export'` in the Next.js config |
| `next-font-package` | The `@next/font` package is removed | The built-in `next/font` |
| `next-og-image-response` | `ImageResponse` moved out of `next/server` | Import from `next/og` |

Needs Node.js 18.17 or later.

### 14 to 15

| Rule id | Change in 15 | Replacement |
|---|---|---|
| `next-experimental-edge` | The `experimental-edge` runtime value is rejected | `edge` |
| `next-sync-request-api` (deprecated in 15) | `cookies()`, `headers()` and `draftMode()` return promises | `await` the call |

With no rule:

- `params` and `searchParams` are promises too, in pages, layouts, route
  handlers and metadata functions. The official codemod handles many cases
  and leaves a comment where it cannot.
- Caching defaults changed: `fetch` requests, `GET` route handlers and the
  client router cache are no longer cached by default. Code that relied on
  the old defaults keeps running and behaves differently.
- React 19 arrives in this stage for App Router projects, so the React 18 to
  19 table above applies here.

### 15 to 16

| Rule id | Change in 16 | Replacement |
|---|---|---|
| `next-sync-request-api` (review) | Synchronous access to the request APIs is removed | `await` the call |
| `next-lint-script` | The `next lint` command is removed | Run the linter directly |
| `next-amp` | AMP support is removed | Remove the AMP usage |

Needs Node.js 20.9 or later. Turbopack is the default bundler, so a project
with a custom webpack configuration needs a decision before this stage. The
version 16 guide lists further removals; read it.

## Angular

Guide: the interactive [Angular update guide](https://angular.dev/update-guide)
(choose the two versions and it lists the steps). Supported Node.js,
TypeScript and RxJS ranges for each major:
[version compatibility](https://angular.dev/reference/versions).

Angular is different from React and Next.js in one way that matters here:
`ng update` applies each major's migrations itself. Most source changes are
made by those migrations, so the rule table is short on purpose and the
update guide is the main source.

| Rule id | Change | Replacement |
|---|---|---|
| `angular-http-package` | `@angular/http` is removed in 8 | `HttpClient` from `@angular/common/http` |
| `angular-view-engine-opt-out` | `"enableIvy": false` cannot work from 13, which removes View Engine | Remove the option; build with Ivy |
| `angular-entry-components` | `entryComponents` is removed in 16 (unneeded since Ivy in 9) | Delete the array |
| `angular-material-legacy` | `@angular/material/legacy-*` is deprecated in Material 15 and removed in Material 17 | The MDC-based components |

Stage facts with no rule:

- 9: Ivy becomes the default compiler and renderer.
- 13: View Engine is removed. Internet Explorer 11 is no longer supported.
- 16: the compatibility compiler (ngcc) is removed, so a library published
  only in View Engine format stops working. Check old libraries before this
  stage.
- 19: components, directives and pipes are standalone by default. `ng update`
  adds `standalone: false` to existing NgModule-based declarations.

Family rule: every `@angular/*` framework package is on the same version as
`@angular/core`, and `@angular/cdk` matches `@angular/material`. The scan
reports any that differ.

## What the scan does not see

- Behaviour changes that keep the same API (batching, caching defaults, event
  delegation, effect timing).
- Type-level breaks. The type-check finds those.
- Changes inside configuration files other than `package.json` scripts and
  `tsconfig*.json`.
- Templates in `.html` files, styles, and anything generated at build time.
- Third-party libraries that broke without declaring a peer range.
- Majors newer than the rule table. For those stages the scan prints the
  path, the family and "the rule table has 0 rule(s) for this stage".
