# Site power and environment

## Establish how long the site can run unattended
Applies to: POWER_UNSTABLE

1. Read the remaining battery autonomy from the site power controller. This
   number, not the alarm itself, decides how urgent the dispatch is.
2. Check whether the rectifier is charging. A site on batteries with no charge
   current will go down, and the only question is when.
3. Record the expected time to exhaustion on the incident so the field team can
   be scheduled against it.

## Respond to a cooling failure
Applies to: TEMPERATURE_HIGH

1. Confirm the reading against a second sensor before dispatching, because a
   single failed sensor is more common than a genuine cooling failure.
2. If the temperature is genuinely rising, check for a tripped air-conditioning
   breaker before assuming the unit has failed.
3. Equipment will begin shutting itself down to protect its hardware once the
   cabinet passes its thermal limit. Treat a confirmed rise as urgent.

## Restore a cell that has stopped carrying traffic
Applies to: CELL_OUT_OF_SERVICE

1. Establish whether the cell is isolated or genuinely faulty. A cell behind a
   failed backhaul link is a symptom, and restarting it will not help.
2. Check the radio unit's operational state and its power feed before
   attempting any reset.
3. Attempt a remote reset only when transport and power are both confirmed
   healthy, and only with the change approved.

## Never reset equipment blind
Applies to: CELL_OUT_OF_SERVICE, POWER_UNSTABLE, TEMPERATURE_HIGH
Requires: supervisor

1. A reset destroys the diagnostic state that explains the fault. Capture logs
   and counters first.
2. A site already running on battery may not come back after a reset. Confirm
   the power state before issuing one.
3. Resets on a site carrying emergency-services traffic require supervisor
   approval regardless of severity.
