"""
A collection of back end subroutines (mostly SQL queries).

This module contains the routines to deal with flagging and monitoring
of transient candidates, mostly involving the monitoringlist.
"""
import logging
from collections import namedtuple
import time

from tkp.db import general
import tkp.db


logger = logging.getLogger(__name__)
logdir = '/export/scratch2/bscheers/lofar/release1/performance/feb2013-sp6/napels/test/run_0/log'


def get_nulldetections(image_id, deRuiter_r):
    """
    Returns the runningcatalog sources which:

      * Do not have a counterpart in the extractedsources of the current
        image;
      * Have been seen (in any band) in a timestep earlier than that of the
        current image.

    NB This is run *prior* to source association.

    We do not have to take into account associations with monitoringlist
    sources, since they have been added to extractedsources at the beginning
    of the association procedures (marked as extract_type=1 sources), and so
    they must have an occurence in extractedsource and runcat.
    
    That is, we determine null detections only as those sources which have been
    seen at earlier times which don't appear in the current image. Sources which
    have not been seen earlier, and which appear in different bands at the current
    timestep, are *not* null detections.

    Output: list of tuples [(runcatid, ra, decl)]
    """
    
    # The first temptable t0 looks for runcat sources in the same or adjacent 
    # sky regions in which the extracted sources were found.
    # The second temptable t1 returns the runcat source ids for those sources 
    # that have an association with the current extracted sources.
    # The left outer join in combination with the t1.id IS NULL then
    # returns the runcat sources that could not be associated.
    
    query = """\
SELECT t0.id
      ,t0.wm_ra
      ,t0.wm_decl
  FROM (SELECT r1.id
              ,r1.wm_ra
              ,r1.wm_decl
          FROM image i1
              ,runningcatalog r1
              ,assocskyrgn a1
              ,extractedsource x1
              ,image i2
         WHERE i1.id = %(image_id)s
           AND r1.dataset = i1.dataset
           AND a1.skyrgn = i1.skyrgn
           AND r1.id = a1.runcat
           AND x1.id = r1.xtrsrc
           AND i2.id = x1.image
           AND i1.taustart_ts > i2.taustart_ts
       ) t0
       LEFT OUTER JOIN (SELECT r1.id
                          FROM image i1
                              ,runningcatalog r1
                              ,assocskyrgn a1
                              ,extractedsource x1
                              ,image i2
                              ,extractedsource x2
                         WHERE i1.id = %(image_id)s
                           AND r1.dataset = i1.dataset
                           AND a1.skyrgn = i1.skyrgn
                           AND r1.id = a1.runcat
                           AND x1.id = r1.xtrsrc
                           AND i2.id = x1.image
                           AND i1.taustart_ts > i2.taustart_ts
                           AND x2.image = %(image_id)s
                           AND r1.zone BETWEEN CAST(FLOOR(x2.decl - i1.rb_smaj) AS INTEGER)
                                           AND CAST(FLOOR(x2.decl + i1.rb_smaj) AS INTEGER)
                           AND r1.wm_decl BETWEEN x2.decl - i1.rb_smaj
                                              AND x2.decl + i1.rb_smaj
                           AND r1.wm_ra BETWEEN x2.ra - alpha(i1.rb_smaj, x2.decl)
                                            AND x2.ra + alpha(i1.rb_smaj, x2.decl)
                           AND SQRT(  (x2.ra - r1.wm_ra) * COS(RADIANS((x2.decl + r1.wm_decl)/2))
                                    * (x2.ra - r1.wm_ra) * COS(RADIANS((x2.decl + r1.wm_decl)/2))
                                    / (x2.uncertainty_ew * x2.uncertainty_ew + r1.wm_uncertainty_ew * r1.wm_uncertainty_ew)
                                   + (x2.decl - r1.wm_decl) * (x2.decl - r1.wm_decl)
                                    / (x2.uncertainty_ns * x2.uncertainty_ns + r1.wm_uncertainty_ns * r1.wm_uncertainty_ns)
                                   ) < %(drrad)s
       ) t1
       ON t0.id = t1.id
 WHERE t1.id IS NULL
"""    
    qry_params = {'image_id':image_id, 'drrad': deRuiter_r}
    logfile = open(logdir + '/' + get_nulldetections.__name__ + '.log', 'a')
    start = time.time()
    cursor = tkp.db.execute(query, qry_params)
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    results = zip(*cursor.fetchall())
    if len(results) != 0:
        return zip(list(results[1]), list(results[2]))
        #maxbeam = max(results[3][0],results[4][0]) # all bmaj & bmin are the same
    else:
        return []


def adjust_transients_in_monitoringlist(image_id, transients):
    """Adjust transients in monitoringlist, by either adding or
    updating them

    """
    _update_known_transients_in_monitoringlist(image_id, transients)
    _insert_new_transients_in_monitoringlist(image_id)


def _update_known_transients_in_monitoringlist(image_id, transients):
    """Update transients in monitoringlist"""
    query = """\
    UPDATE monitoringlist
       SET ra = %(wm_ra)s
          ,decl = %(wm_decl)s
      WHERE runcat = %(runcat)s
    """
    upd = 0
    logfile = open(logdir + '/' + _update_known_transients_in_monitoringlist.__name__ + '.log', 'a')
    start = time.time()
    
    for entry in transients:
        cursor = tkp.db.execute(query, entry, commit=False)
        upd += cursor.rowcount
    tkp.db.commit()
    
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    
    if upd > 0:
        logger.info("Updated %s known transients in monitoringlist" % (upd,))


def _insert_new_transients_in_monitoringlist(image_id):
    """
    Copy newly identified transients from transients table into monitoringlist.

    We grab the transients and check that their runcat ids are not in the
    monitoringlist.
    """
    query = """\
INSERT INTO monitoringlist
  (runcat
  ,ra
  ,decl
  ,dataset
  )
  SELECT t.runcat
        ,r.wm_ra
        ,r.wm_decl
        ,r.dataset
    FROM transient t
        ,runningcatalog r
        ,image i
   WHERE t.runcat = r.id
     AND r.dataset = i.dataset
     AND i.id = %(image_id)s
     AND t.runcat NOT IN (SELECT m0.runcat
                            FROM monitoringlist m0
                                ,runningcatalog r0
                                ,image i0
                           WHERE m0.runcat = r0.id
                             AND r0.dataset = i0.dataset
                             AND i0.id = %(image_id)s
                         )
"""
    logfile = open(logdir + '/' + _insert_new_transients_in_monitoringlist.__name__ + '.log', 'a')
    start = time.time()
    cursor = tkp.db.execute(query, {'image_id': image_id}, commit=True)
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    ins = cursor.rowcount
    if ins == 0:
        logger.info("No new transients inserted in monitoringlist")
    else:
        logger.info("Inserted %s new transients in monitoringlist" % (ins,))


def add_nulldetections(image_id):
    """
    Add null detections (intermittent) sources to monitoringlist.

    Null detections are picked up by the source association and
    added to extractedsource table to undergo normal processing.

    Variable or not, intermittent sources are interesting enough
    to be added to the monitoringlist.

    Insert checks whether runcat ref of source exists
    """

    # TODO:
    # Do we need to take care of updates here as well (like the adjust_transients)?
    # Or is that correctly done in update monlist

    # Optimise by using image_id for image and extractedsource
    # extract_type = 1 -> the null detections (forced fit) in extractedsource
    #Note extra clauses on image id ARE necessary (MonetDB performance quirks)
    query = """\
INSERT INTO monitoringlist
  (runcat
  ,ra
  ,decl
  ,dataset
  )
  SELECT r.id AS runcat
        ,r.wm_ra AS ra
        ,r.wm_decl AS decl
        ,r.dataset
    FROM extractedsource x
        ,image i
        ,runningcatalog r
        ,assocxtrsource a
   WHERE x.image = %(image_id)s
     AND x.image = i.id
     AND i.id = %(image_id)s
     AND i.dataset = r.dataset
     AND r.id = a.runcat
     AND a.xtrsrc = x.id
     AND x.extract_type = 1
     AND NOT EXISTS (SELECT m0.runcat
                       FROM extractedsource x0
                           ,image i0
                           ,runningcatalog r0
                           ,assocxtrsource a0
                           ,monitoringlist m0
                      WHERE x0.image = %(image_id)s
                        AND x0.image = i0.id
                        AND i0.id = %(image_id)s
                        AND i0.dataset = r0.dataset
                        AND r0.id = a0.runcat
                        AND a0.xtrsrc = x0.id
                        AND x0.extract_type = 1
                        AND r0.id = m0.runcat
                    )
"""
    logfile = open(logdir + '/' + add_nulldetections.__name__ + '.log', 'a')
    start = time.time()
    cursor = tkp.db.execute(query, {'image_id': image_id}, commit=True)
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    ins = cursor.rowcount
    if ins > 0:
        logger.info("Added %s forced fit null detections to monlist" % (ins,))


def add_manual_entry_to_monitoringlist(dataset_id, ra, dec):
    """
    Add manual entry to monitoringlist.

    In this case, the runcat_id defaults to null initially,
    since there is no associated source yet.
    (This is updated when we perform our first forced extraction
    at these co-ordinates.)
    """
    query = """\
INSERT INTO monitoringlist
  (ra
  ,decl
  ,dataset
  ,userentry
  )
  SELECT %s
        ,%s
        ,%s
        ,TRUE
"""
    cursor = tkp.db.execute(query, commit=True)
