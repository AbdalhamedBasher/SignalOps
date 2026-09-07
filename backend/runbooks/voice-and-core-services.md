# Voice and core services

## Separate a VoLTE fault from a transport fault
Applies to: VOLTE_REG_FAILURE

1. Check whether the site's control-plane link to the core is healthy. VoLTE
   registration failures are usually a symptom of transport loss rather than a
   fault in the voice platform.
2. Confirm whether registrations are failing at one site or across several. A
   single site points at access; many sites point at the core.
3. Only involve the IMS on-call engineer once transport has been ruled out.

## Protect emergency calling
Applies to: VOLTE_REG_FAILURE, CELL_OUT_OF_SERVICE
Requires: supervisor

1. Confirm whether subscribers at the affected site can still reach emergency
   services through circuit-switched fallback.
2. If emergency calling is impaired, escalate immediately and treat the
   incident as critical regardless of the subscriber count.
3. Record the time emergency calling was confirmed impaired, because it is
   reportable to the regulator.
