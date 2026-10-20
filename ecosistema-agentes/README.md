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
| Motor de políticas | `governance/policy.py` | Reglas ALLOW/DENY declarativas (estilo IAM) por rol, acción y recurso, con patrones glob. Denegación por defecto; un DENY explícito siempre gana. Cargables desde JSON versionable. |
| Auditoría | `governance/audit.py` | Registro append-only con encadenamiento SHA-256: cualquier manipulación retroactiva se detecta con `verify_integrity()`. |
| Límites de uso | `governance/limits.py` | Cuota de acciones y presupuesto de coste por agente en ventanas de tiempo. |
| Registro de agentes | `orchestration/registry.py` | Directorio oficial: solo los agentes registrados reciben tareas; se indexa por capacidad. |
| Orquestador | `orchestration/orchestrator.py` | Aplica todo lo anterior en cada acción, gestiona la cola de aprobaciones humanas (o de agentes con rol supervisor) y ejecuta las herramientas reales. |

## Uso rápido

```bash
# Ejecutar la demo (investigador + redactor + agente externo malicioso)
python examples/demo.py

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
│   ├── governance/      # identidad, políticas, auditoría, límites
│   └── orchestration/   # registro de agentes y orquestador
├── policies/            # políticas declarativas en JSON
├── examples/demo.py     # escenario completo de demostración
└── tests/               # pruebas unitarias y de integración
```

## Posibles extensiones

- Ejecución asíncrona y colas de mensajes entre agentes.
- Persistencia de la auditoría (SQLite / almacén append-only externo).
- Políticas con condiciones sobre parámetros (p. ej. límites por destinatario).
- Integración con modelos de lenguaje reales como "cerebro" de cada agente.
- Panel web para la cola de aprobaciones y la pista de auditoría.
