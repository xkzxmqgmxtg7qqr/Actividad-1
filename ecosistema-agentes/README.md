# Ecosistema de agentes gobernados

Prototipo funcional de un ecosistema multi-agente con **gobernanza integrada**: los agentes de IA no actúan libremente, sino dentro de un marco de identidad, políticas, límites, aprobación humana y auditoría que el código del agente no puede eludir.

Escrito en Python puro (sin dependencias externas, Python ≥ 3.10).

## Idea central

Los agentes **nunca ejecutan acciones directamente**. Declaran lo que quieren hacer a través de un `ActionContext` y el **orquestador** decide:

```
Agente ── solicita acción ──> Orquestador
                                 │ 1. Motor de políticas (denegación por defecto)
                                 │ 2. Límites de uso (cuota y presupuesto)
                                 │ 3. ¿Requiere aprobación humana? → cola de aprobación
                                 │ 4. Ejecución de la herramienta real
                                 ▼
                             Auditoría (cadena de hashes, inmutable)
```

## Componentes

| Componente | Módulo | Responsabilidad |
|---|---|---|
| Identidad y roles | `governance/identity.py` | Cada agente tiene id, propietario, rol (`supervisor`, `trusted`, `standard`, `sandboxed`) y capacidades declaradas. |
| Motor de políticas | `governance/policy.py` | Reglas ALLOW/DENY declarativas (estilo IAM) por rol, acción y recurso, con patrones glob y **condiciones sobre los parámetros de la acción** (p. ej. importe máximo o lista de destinatarios autorizados). Denegación por defecto; un DENY explícito siempre gana. Cargables desde JSON versionable. |
| Auditoría | `governance/audit.py` | Registro append-only con encadenamiento SHA-256: cualquier manipulación retroactiva se detecta con `verify_integrity()`. |
| Límites de uso | `governance/limits.py` | Cuota de acciones y presupuesto de coste por agente en ventanas de tiempo. |
| Auditoría persistente | `governance/audit_sqlite.py` | Misma cadena de hashes sobre SQLite: los eventos sobreviven a reinicios y la manipulación directa de la base de datos se detecta al verificar. |
| Registro de agentes | `orchestration/registry.py` | Directorio oficial: solo los agentes registrados reciben tareas; se indexa por capacidad. |
| Orquestador | `orchestration/orchestrator.py` | Aplica todo lo anterior en cada acción, gestiona la cola de aprobaciones humanas (o de agentes con rol supervisor), media la delegación entre agentes y ejecuta las herramientas reales. |
| Panel web | `panel/server.py` | Interfaz para el humano en el circuito: aprobar/rechazar acciones pendientes y revisar la pista de auditoría con su estado de integridad. |
| Cerebros LLM | `llm/providers.py` | Las llamadas al modelo son acciones gobernadas (`llm.generate` sobre `model/<nombre>`): políticas por rol y modelo, presupuesto y auditoría. Incluye un proveedor simulado (sin red) y un cliente compatible con OpenAI (solo stdlib). |

### Políticas condicionales

Una política puede exigir condiciones sobre los parámetros de la acción, tanto en código (`Condition("amount", "lte", 500)`) como en JSON:

```json
{
  "policy_id": "pagos-pequenos",
  "effect": "allow",
  "actions": ["pay.transfer"],
  "conditions": [
    {"param": "recipient", "op": "in", "value": ["proveedor-a", "proveedor-b"]},
    {"param": "amount", "op": "lte", "value": 500}
  ]
}
```

Operadores: `eq`, `ne`, `in`, `not_in`, `lt`, `lte`, `gt`, `gte` y `matches` (glob sobre cadenas). Si el parámetro falta o los tipos no son comparables, la condición no se cumple y la política no aplica (lo que, con denegación por defecto, bloquea la acción).

### Agentes con cerebro LLM

El proveedor LLM se registra como una herramienta más del orquestador, de modo que los agentes lo usan vía `context.act("llm.generate", "model/<nombre>", {"prompt": ...}, cost=...)` y las llamadas quedan sujetas a políticas (qué roles usan qué modelos), presupuesto y auditoría:

```python
from governed_agents.llm.providers import MockLlmProvider, OpenAiCompatibleProvider, create_llm_tool

orchestrator.register_tool("llm.generate", create_llm_tool(MockLlmProvider()))
# o con un modelo real (clave en OPENAI_API_KEY):
# orchestrator.register_tool("llm.generate", create_llm_tool(OpenAiCompatibleProvider()))
```

### Delegación gobernada entre agentes

Un agente puede encargar subtareas a otro con `context.delegate(capacidad, payload)`, pero la delegación es en sí misma una acción gobernada (`agent.delegate` sobre `capability/<capacidad>`): puede denegarse por política (por defecto solo los roles `trusted` y `supervisor` delegan) y está sujeta a un límite de profundidad (`max_delegation_depth`) que corta cadenas de delegación infinitas. Cada subtarea queda auditada con quién la pidió y a qué profundidad.

## Uso rápido

```bash
# Demo básica (investigador + redactor + agente externo malicioso)
python examples/demo.py

# Demo de delegación gobernada y auditoría persistente en SQLite
python examples/demo_fase2.py

# Demo de LLM gobernado y políticas condicionales (pagos con límites)
python examples/demo_fase3.py

# Panel web de aprobaciones en http://127.0.0.1:8765
python examples/demo_panel.py

# Ejecutar las pruebas
python -m unittest discover -s tests -v
```

## Ejemplo mínimo

```python
from governed_agents import (
    Agent, AgentIdentity, AgentRegistry, Effect, Orchestrator,
    Policy, PolicyEngine, Role, Task,
)

class Investigador(Agent):
    def handle(self, task, context):
        return context.act("web.search", f"query/{task.payload['q']}", cost=0.5)

registry = AgentRegistry()
registry.register(Investigador(AgentIdentity("inv-1", Role.TRUSTED, ("research",))))

engine = PolicyEngine([
    Policy("lectura", Effect.ALLOW, actions=("web.search",)),
    Policy("correo", Effect.ALLOW, actions=("email.send",), requires_approval=True),
])

orchestrator = Orchestrator(registry, engine)
result = orchestrator.submit(Task("research", {"q": "gobernanza de IA"}))
print(result.status)                        # "completed"
print(orchestrator.audit.verify_integrity())  # True
```

Las políticas también pueden definirse en JSON (ver `policies/default_policies.json`) y cargarse con `PolicyEngine.from_json(ruta)`, lo que permite revisarlas y versionarlas igual que el código.

## Garantías de gobernanza

1. **Denegación por defecto**: una acción sin política ALLOW aplicable se rechaza.
2. **DENY absoluto**: una política DENY no puede ser anulada por ningún ALLOW.
3. **Mediación total**: el agente solo actúa a través del `ActionContext` que le entrega el orquestador; no hay vía directa a las herramientas.
4. **Humano en el circuito**: cualquier política puede exigir aprobación (`requires_approval`), que resuelve un humano o un agente con rol `supervisor`.
5. **Trazabilidad verificable**: todos los eventos (tareas, permisos, denegaciones, aprobaciones, fallos) quedan en una cadena de auditoría con integridad criptográfica.
6. **Contención de recursos**: cuotas de acciones y presupuesto por agente y ventana de tiempo.

## Estructura

```
ecosistema-agentes/
├── src/governed_agents/
│   ├── core/            # Agent, ActionContext, Task, ActionRequest
│   ├── governance/      # identidad, políticas (con condiciones), auditoría, límites
│   ├── orchestration/   # registro de agentes, orquestador y delegación
│   ├── llm/             # proveedores LLM gobernados (mock y compatible OpenAI)
│   └── panel/           # panel web de aprobaciones y auditoría
├── policies/            # políticas declarativas en JSON
├── examples/            # demos: básica, delegación/persistencia y panel web
└── tests/               # pruebas unitarias y de integración
```

## Posibles extensiones

- Ejecución asíncrona y colas de mensajes entre agentes.
- Autenticación y roles de usuario en el panel web.
- Coste real de las llamadas LLM reconciliado con el presupuesto (hoy se usa el coste declarado por el agente).
- Streaming y herramientas (function calling) en el cliente LLM.
