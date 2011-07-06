# -*- coding: utf-8 -*-

#
# LOFAR Transients Key Project
#
import sys, pylab
from scipy import *
from scipy import optimize
import numpy as np
# Local tkp_lib functionality
import monetdb.sql as db
import logging
from tkp.config import config

DERUITER_R = config['source_association']['deruiter_radius']

def cross_associate_cataloged_sources(conn 
                                     ,c
                                     ,ra_min 
                                     ,ra_max 
                                     ,decl_min 
                                     ,decl_max 
                                     ,deRuiter_r=None 
                                     ):

    if not deRuiter_r:
        deRuiter_r = DERUITER_R
        
    # I know the cat_id's of the VLSS, WENSSm, WENSSp and NVSS, resp.
    #c = [4, 5, 6, 3]
    #c = [3, 4, 5, 6]
    #c = [4, 5, 6, 3]
    for i in range(len(c)):
        print "Busy with cat_id = ", c[i]
        _empty_selected_catsources(conn)
        _empty_tempmergedcatalogs(conn)
        _insert_selected_catsources(conn, c[i], ra_min, ra_max, decl_min, decl_max)
        _insert_tempmergedcatalogs(conn, c[i], ra_min, ra_max, decl_min, decl_max, deRuiter_r)
        _flag_multiple_counterparts_in_mergedcatalogs(conn)
        _insert_multiple_crossassocs(conn)
        _insert_first_of_multiple_crossassocs(conn)
        _flag_swapped_multiple_crossassocs(conn)
        _insert_multiple_crossassocs_mergedcat(conn)
        _flag_old_multiple_assocs_mergedcat(conn)
        _flag_multiple_assocs(conn)
        #+-----------------------------------------------------+
        #| After all this, we are now left with the 1-1 assocs |
        #+-----------------------------------------------------+
        _insert_single_crossassocs(conn)
        _update_mergedcatalogs(conn)
        _empty_tempmergedcatalogs(conn)
        _count_known_sources(conn, deRuiter_r)
        _insert_new_assocs(conn, deRuiter_r)
        _insert_new_source_mergedcatalogs(conn, c[i], ra_min, ra_max, decl_min, decl_max, deRuiter_r)
        #if i > 0:
        #    sys.exit('Stopppp')
    _empty_selected_catsources(conn)
    _update_fluxes_mergedcatalogs(conn, c)
    _update_spectralindices_mergedcatalogs(conn, c)

def _empty_selected_catsources(conn):
    """Initialize the temporary storage table

    Initialize the temporary table temprunningcatalog which contains
    the current observed sources.
    """

    try:
        cursor = conn.cursor()
        query = """DELETE FROM selectedcatsources"""
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()

def _empty_tempmergedcatalogs(conn):
    """Initialize the temporary storage table

    Initialize the temporary table temprunningcatalog which contains
    the current observed sources.
    """

    try:
        cursor = conn.cursor()
        query = """DELETE FROM tempmergedcatalogs"""
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()

def _insert_selected_catsources(conn, cat_id, ra_min, ra_max, decl_min, decl_max):
    """Select matched sources

    Here we select the extractedsources that have a positional match
    with the sources in the running catalogue table (runningcatalog)
    and those who have will be inserted into the temporary running
    catalogue table (temprunningcatalog).

    Explanation of some columns used in the SQL query:

    - avg_I_peak := average of I_peak
    - avg_I_peak_sq := average of I_peak^2
    - avg_weight_I_peak := average of weight of I_peak, i.e. 1/error^2
    - avg_weighted_I_peak := average of weighted i_peak,
         i.e. average of I_peak/error^2
    - avg_weighted_I_peak_sq := average of weighted i_peak^2,
         i.e. average of I_peak^2/error^2

    This result set might contain multiple associations (1-n,n-1)
    for a single known source in runningcatalog.

    The n-1 assocs will be treated similar as the 1-1 assocs.
    """

    try:
        cursor = conn.cursor()
        # !!TODO!!: Add columns for previous weighted averaged values,
        # otherwise the assoc_r will be biased.
        query = """\
INSERT INTO selectedcatsources
  (catsrc_id
  ,cat_id
  ,zone
  ,ra
  ,decl
  ,ra_err
  ,decl_err
  ,x
  ,y
  ,z
  ,i_peak
  ,i_peak_err
  ,i_int
  ,i_int_err
  )
  SELECT c0.catsrcid
        ,c0.cat_id
        ,c0.zone
        ,c0.ra
        ,c0.decl
        ,c0.ra_err
        ,c0.decl_err
        ,c0.x
        ,c0.y
        ,c0.z
        ,c0.i_peak_avg
        ,c0.i_peak_avg_err
        ,c0.i_int_avg
        ,c0.i_int_avg_err
    FROM catalogedsources c0
   WHERE c0.cat_id = %s
     AND c0.zone BETWEEN CAST(FLOOR(CAST(%s AS DOUBLE) - 0.025) as INTEGER)
                     AND CAST(FLOOR(CAST(%s AS DOUBLE) + 0.025) as INTEGER)
     AND c0.decl BETWEEN CAST(%s AS DOUBLE) - 0.025
                     AND CAST(%s AS DOUBLE) + 0.025
     AND c0.ra BETWEEN CAST(%s AS DOUBLE) - alpha(0.025, %s)
                   AND CAST(%s AS DOUBLE) + alpha(0.025, %s)
"""
        cursor.execute(query, (cat_id 
                              ,decl_min 
                              ,decl_max
                              ,decl_min
                              ,decl_max
                              ,ra_min
                              ,decl_max
                              ,ra_max
                              ,decl_max
                              ))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()

def _insert_tempmergedcatalogs(conn, cat_id, ra_min, ra_max, decl_min, decl_max, deRuiter_r):
    """Select matched sources

    Here we select the extractedsources that have a positional match
    with the sources in the running catalogue table (runningcatalog)
    and those who have will be inserted into the temporary running
    catalogue table (temprunningcatalog).

    Explanation of some columns used in the SQL query:

    - avg_I_peak := average of I_peak
    - avg_I_peak_sq := average of I_peak^2
    - avg_weight_I_peak := average of weight of I_peak, i.e. 1/error^2
    - avg_weighted_I_peak := average of weighted i_peak,
         i.e. average of I_peak/error^2
    - avg_weighted_I_peak_sq := average of weighted i_peak^2,
         i.e. average of I_peak^2/error^2

    This result set might contain multiple associations (1-n,n-1)
    for a single known source in runningcatalog.

    The n-1 assocs will be treated similar as the 1-1 assocs.
    """

    try:
        cursor = conn.cursor()
        # !!TODO!!: Add columns for previous weighted averaged values,
        # otherwise the assoc_r will be biased.
        query = """\
INSERT INTO tempmergedcatalogs
  (catsrc_id
  ,assoc_catsrc_id
  ,assoc_cat_id
  ,datapoints
  ,zone
  ,wm_ra
  ,wm_decl
  ,wm_ra_err
  ,wm_decl_err
  ,avg_wra
  ,avg_wdecl
  ,avg_weight_ra
  ,avg_weight_decl
  ,x
  ,y
  ,z
  ,i_peak
  ,i_int
  )
  SELECT t0.catsrc_id
        ,t0.assoc_catsrc_id
        ,t0.assoc_cat_id
        ,t0.datapoints
        ,CAST(FLOOR(t0.wm_decl/1) AS INTEGER)
        ,t0.wm_ra
        ,t0.wm_decl
        ,t0.wm_ra_err
        ,t0.wm_decl_err
        ,t0.avg_wra
        ,t0.avg_wdecl
        ,t0.avg_weight_ra
        ,t0.avg_weight_decl
        ,COS(rad(t0.wm_decl)) * COS(rad(t0.wm_ra))
        ,COS(rad(t0.wm_decl)) * SIN(rad(t0.wm_ra))
        ,SIN(rad(t0.wm_decl))
        ,i_peak
        ,i_int
    FROM (SELECT m0.catsrc_id as catsrc_id
                ,s0.catsrc_id as assoc_catsrc_id
                ,s0.cat_id as assoc_cat_id
                ,m0.datapoints + 1 AS datapoints
                ,((m0.datapoints * m0.avg_wra + s0.ra /
                  (s0.ra_err * s0.ra_err)) / (datapoints + 1))
                 /
                 ((datapoints * m0.avg_weight_ra + 1 /
                   (s0.ra_err * s0.ra_err)) / (datapoints + 1))
                 AS wm_ra
                ,((datapoints * m0.avg_wdecl + s0.decl /
                  (s0.decl_err * s0.decl_err)) / (datapoints + 1))
                 /
                 ((datapoints * m0.avg_weight_decl + 1 /
                   (s0.decl_err * s0.decl_err)) / (datapoints + 1))
                 AS wm_decl
                ,SQRT(1 / ((datapoints + 1) *
                  ((datapoints * m0.avg_weight_ra +
                    1 / (s0.ra_err * s0.ra_err)) / (datapoints + 1))
                          )
                     ) AS wm_ra_err
                ,SQRT(1 / ((datapoints + 1) *
                  ((datapoints * m0.avg_weight_decl +
                    1 / (s0.decl_err * s0.decl_err)) / (datapoints + 1))
                          )
                     ) AS wm_decl_err
                ,(datapoints * m0.avg_wra + s0.ra / (s0.ra_err * s0.ra_err))
                 / (datapoints + 1) AS avg_wra
                ,(datapoints * m0.avg_wdecl + s0.decl / (s0.decl_err * s0.decl_err))
                 / (datapoints + 1) AS avg_wdecl
                ,(datapoints * m0.avg_weight_ra + 1 /
                  (s0.ra_err * s0.ra_err))
                 / (datapoints + 1) AS avg_weight_ra
                ,(datapoints * m0.avg_weight_decl + 1 /
                  (s0.decl_err * s0.decl_err))
                 / (datapoints + 1) AS avg_weight_decl
                ,s0.i_peak
                ,s0.i_int
            FROM mergedcatalogs m0
                ,selectedcatsources s0
           WHERE s0.cat_id = %s
             AND s0.zone BETWEEN CAST(FLOOR(CAST(%s AS DOUBLE) - 0.025) as INTEGER)
                             AND CAST(FLOOR(CAST(%s AS DOUBLE) + 0.025) as INTEGER)
             AND s0.decl BETWEEN CAST(%s AS DOUBLE) - 0.025
                             AND CAST(%s AS DOUBLE) + 0.025
             AND s0.ra BETWEEN CAST(%s AS DOUBLE) - alpha(0.025, %s)
                           AND CAST(%s AS DOUBLE) + alpha(0.025, %s)
             AND m0.zone BETWEEN CAST(FLOOR(CAST(%s AS DOUBLE) - 0.025) as INTEGER)
                             AND CAST(FLOOR(CAST(%s AS DOUBLE) + 0.025) as INTEGER)
             AND m0.wm_decl BETWEEN CAST(%s AS DOUBLE) - 0.025
                                AND CAST(%s AS DOUBLE) + 0.025
             AND m0.wm_ra BETWEEN CAST(%s AS DOUBLE) - alpha(0.025, %s)
                              AND CAST(%s AS DOUBLE) + alpha(0.025, %s)
             AND m0.x * s0.x + m0.y * s0.y + m0.z * s0.z > COS(rad(0.025))
             AND SQRT(  (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
                      * (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
                      / (s0.ra_err * s0.ra_err + m0.wm_ra_err * m0.wm_ra_err)
                     + (s0.decl - m0.wm_decl) * (s0.decl - m0.wm_decl)
                      / (s0.decl_err * s0.decl_err + m0.wm_decl_err * m0.wm_decl_err)
                     ) < %s
         ) t0
"""
        cursor.execute(query, (cat_id 
                              ,decl_min
                              ,decl_max
                              ,decl_min
                              ,decl_max
                              ,ra_min
                              ,decl_max
                              ,ra_max
                              ,decl_max
                              ,decl_min
                              ,decl_max
                              ,decl_min
                              ,decl_max
                              ,ra_min
                              ,decl_max
                              ,ra_max
                              ,decl_max
                              ,deRuiter_r 
                              ))
        #if image_id == 2:
        #    raise
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        hv = [cat_id
             ,decl_min
             ,decl_max
             ,decl_min
             ,decl_max
             ,ra_min
             ,decl_max
             ,ra_max
             ,decl_max
             ,decl_min
             ,decl_max
             ,decl_min
             ,decl_max
             ,ra_min
             ,decl_max
             ,ra_max
             ,decl_max
             ,deRuiter_r 
             ]
        logging.warn("host variables: %s" % hv)
        raise
    finally:
        cursor.close()


def _flag_multiple_counterparts_in_mergedcatalogs(conn):
    """Flag source with multiple associations

    Before we continue, we first take care of the sources that have
    multiple associations in both directions.

    -1- running-catalogue sources  <- extracted source

    An extracted source has multiple counterparts in the running
    catalogue.  We only keep the ones with the lowest deRuiter_r
    value, the rest we throw away.

    NOTE:

    It is worth considering whether this might be changed to selecting
    the brightest neighbour source, instead of just the closest
    neighbour.

    (There are case [when flux_lim > 10Jy] that the nearest source has
    a lower flux level, causing unexpected spectral indices)
    """

    try:
        cursor = conn.cursor()
        query = """\
        SELECT t1.catsrc_id
              ,t1.assoc_catsrc_id
          FROM (SELECT tm0.assoc_catsrc_id
                      ,MIN(SQRT((s0.ra - m0.wm_ra) * COS(rad(s0.decl))
                                * (s0.ra - m0.wm_ra) * COS(rad(s0.decl))
                                / (s0.ra_err * s0.ra_err + m0.wm_ra_err *
                                   m0.wm_ra_err)
                               + (s0.decl - m0.wm_decl) *
                                 (s0.decl - m0.wm_decl)
                                / (s0.decl_err * s0.decl_err +
                                   m0.wm_decl_err * m0.wm_decl_err)
                               )
                          ) AS min_r1
                  FROM tempmergedcatalogs tm0
                      ,mergedcatalogs m0
                      ,selectedcatsources s0
                 WHERE tm0.assoc_catsrc_id IN (SELECT assoc_catsrc_id
                                                 FROM tempmergedcatalogs
                                               GROUP BY assoc_catsrc_id
                                               HAVING COUNT(*) > 1
                                              )
                   AND tm0.catsrc_id = m0.catsrc_id
                   AND tm0.assoc_catsrc_id = s0.catsrc_id
                GROUP BY tm0.assoc_catsrc_id
               ) t0
              ,(SELECT tm1.catsrc_id
                      ,tm1.assoc_catsrc_id
                      ,SQRT( (s1.ra - m1.wm_ra) * COS(rad(s1.decl))
                            *(s1.ra - m1.wm_ra) * COS(rad(s1.decl))
                            / (s1.ra_err * s1.ra_err +
                               m1.wm_ra_err * m1.wm_ra_err)
                           + (s1.decl - m1.wm_decl) * (s1.decl - m1.wm_decl)
                             / (s1.decl_err * s1.decl_err + m1.wm_decl_err *
                                m1.wm_decl_err)
                           ) AS r1
                  FROM tempmergedcatalogs tm1
                      ,mergedcatalogs m1
                      ,selectedcatsources s1
                 WHERE tm1.assoc_catsrc_id IN (SELECT assoc_catsrc_id
                                                 FROM tempmergedcatalogs
                                               GROUP BY assoc_catsrc_id
                                               HAVING COUNT(*) > 1
                                              )
                   AND tm1.catsrc_id = m1.catsrc_id
                   AND tm1.assoc_catsrc_id = s1.catsrc_id
               ) t1
         WHERE t1.assoc_catsrc_id = t0.assoc_catsrc_id
           AND t1.r1 > t0.min_r1
        """
        cursor.execute(query)
        results = zip(*cursor.fetchall())
        if len(results) != 0:
            catsrc_id = results[0]
            assoc_catsrc_id = results[1]
            # TODO: Consider setting row to inactive instead of deleting
            query = """\
            DELETE
              FROM tempmergedcatalogs
             WHERE catsrc_id = %s
               AND assoc_catsrc_id = %s
            """
            for j in range(len(catsrc_id)):
                cursor.execute(query, (catsrc_id[j], assoc_catsrc_id[j]))
            conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()

def _insert_multiple_crossassocs(conn):
    """Insert sources with multiple associations

    -2- Now, we take care of the sources in the running catalogue that
    have more than one counterpart among the extracted sources.

    We now make two entries in the running catalogue, in stead of the
    one we had before. Therefore, we 'swap' the ids.
    """
    #TODO: check where clause, assoccrosscatsources should have entries for 
    # assoc_lr_method 8 and 9.

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assoccrosscatsources
          (catsrc_id
          ,assoc_catsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT t.assoc_catsrc_id
                ,t.catsrc_id
                ,3600 * deg(2 * ASIN(SQRT((m.x - s.x) * (m.x - s.x)
                                          + (m.y - s.y) * (m.y - s.y)
                                          + (m.z - s.z) * (m.z - s.z)
                                          ) / 2) ) AS assoc_distance_arcsec
                ,3600 * sqrt(
                    ( (m.wm_ra * cos(rad(m.wm_decl)) - s.ra * cos(rad(s.decl)))
                     *(m.wm_ra * cos(rad(m.wm_decl)) - s.ra * cos(rad(s.decl)))
                    ) 
                    / (m.wm_ra_err * m.wm_ra_err + s.ra_err * s.ra_err)
                    + ((m.wm_decl - s.decl) * (m.wm_decl - s.decl)) 
                    / (m.wm_decl_err * m.wm_decl_err + s.decl_err * s.decl_err)
                            ) as assoc_r
                ,9
            FROM tempmergedcatalogs t
                ,mergedcatalogs m
                ,selectedcatsources s
           WHERE t.catsrc_id = m.catsrc_id
             AND t.assoc_catsrc_id = s.catsrc_id
             AND t.catsrc_id IN (SELECT catsrc_id
                                   FROM tempmergedcatalogs
                                 GROUP BY catsrc_id
                                 HAVING COUNT(*) > 1
                                )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_first_of_multiple_crossassocs(conn):
    """Insert identical ids

    -3- And, we have to insert identical ids to identify a light-curve
    starting point.
    """

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assoccrosscatsources
          (catsrc_id
          ,assoc_catsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT assoc_catsrc_id
                ,assoc_catsrc_id
                ,0
                ,0
                ,8
            FROM tempmergedcatalogs
           WHERE catsrc_id IN (SELECT catsrc_id
                                 FROM tempmergedcatalogs
                               GROUP BY catsrc_id
                               HAVING COUNT(*) > 1
                              )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_swapped_multiple_crossassocs(conn):
    """Throw away swapped ids

    -4- And, we throw away the swapped id.

    It might be better to flag this record: consider setting rows to
    inactive instead of deleting
    """
    try:
        cursor = conn.cursor()
        query = """\
        DELETE
          FROM assoccrosscatsources
         WHERE catsrc_id IN (SELECT catsrc_id
                               FROM tempmergedcatalogs
                             GROUP BY catsrc_id
                             HAVING COUNT(*) > 1
                            )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_multiple_crossassocs_mergedcat(conn):
    """Insert new ids of the sources in the running catalogue"""

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO mergedcatalogs
          (catsrc_id
          ,datapoints
          ,zone
          ,wm_ra
          ,wm_decl
          ,wm_ra_err
          ,wm_decl_err
          ,avg_wra
          ,avg_wdecl
          ,avg_weight_ra
          ,avg_weight_decl
          ,x
          ,y
          ,z
          )
          SELECT assoc_catsrc_id
                ,datapoints
                ,zone
                ,wm_ra
                ,wm_decl
                ,wm_ra_err
                ,wm_decl_err
                ,avg_wra
                ,avg_wdecl
                ,avg_weight_ra
                ,avg_weight_decl
                ,x
                ,y
                ,z
            FROM tempmergedcatalogs
           WHERE catsrc_id IN (SELECT catsrc_id
                                 FROM tempmergedcatalogs
                               GROUP BY catsrc_id
                               HAVING COUNT(*) > 1
                              )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_old_multiple_assocs_mergedcat(conn):
    """Here the old assocs in runcat will be deleted."""

    # TODO: Consider setting row to inactive instead of deleting
    try:
        cursor = conn.cursor()
        query = """\
        DELETE
          FROM mergedcatalogs
         WHERE catsrc_id IN (SELECT catsrc_id
                               FROM tempmergedcatalogs
                             GROUP BY catsrc_id
                             HAVING COUNT(*) > 1
                            )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_multiple_assocs(conn):
    """Delete the multiple assocs from the temporary running catalogue table"""

    try:
        cursor = conn.cursor()
        query = """\
        DELETE
          FROM tempmergedcatalogs
         WHERE catsrc_id IN (SELECT catsrc_id
                               FROM tempmergedcatalogs
                             GROUP BY catsrc_id
                             HAVING COUNT(*) > 1
                            )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_single_crossassocs(conn):
    """Insert remaining 1-1 associations into assocxtrsources table"""

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assoccrosscatsources
          (catsrc_id
          ,assoc_catsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT t.catsrc_id
                ,t.assoc_catsrc_id
                ,3600 * deg(2 * ASIN(SQRT((m.x - s.x) * (m.x - s.x)
                                          + (m.y - s.y) * (m.y - s.y)
                                          + (m.z - s.z) * (m.z - s.z)
                                          ) / 2) ) AS assoc_distance_arcsec
                ,3600 * sqrt(
                    ((m.wm_ra * cos(rad(m.wm_decl)) 
                     - s.ra * cos(rad(s.decl))) 
                    * (m.wm_ra * cos(rad(m.wm_decl)) 
                     - s.ra * cos(rad(s.decl)))) 
                    / (m.wm_ra_err * m.wm_ra_err + s.ra_err*s.ra_err)
                    +
                    ((m.wm_decl - s.decl) * (m.wm_decl - s.decl)) 
                    / (m.wm_decl_err * m.wm_decl_err + s.decl_err*s.decl_err)
                            ) as assoc_r
                ,10
            FROM tempmergedcatalogs t
                ,mergedcatalogs m
                ,selectedcatsources s
           WHERE t.catsrc_id = m.catsrc_id
             AND t.assoc_catsrc_id = s.catsrc_id
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _update_mergedcatalogs(conn):
    """Update the running catalog"""

    # Since Jun2010 version we cannot use the massive (but simple) update
    # statement anymore.
    # Therefore, unfortunately, we cursor through the tempsources table
    # TODO: However, it has not been checked yet, whether it is working again
    # in the latest version.
    ##+--------------------------------------------
    ##UPDATE multcatbasesources
    ##  SET zone = (
    ##      SELECT zone
    ##      FROM tempmultcatbasesources
    ##      WHERE tempmultcatbasesources.xtrsrc_id =
    ##            multcatbasesources.xtrsrc_id
    ##      )
    ##     ,ra_avg = (
    ##         SELECT ra_avg
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##         )
    ##     ,decl_avg = (
    ##         SELECT decl_avg
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##         )
    ##     ,ra_err_avg = (
    ##         SELECT ra_err_avg
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##                   )
    ##     ,decl_err_avg = (
    ##         SELECT decl_err_avg
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##                     )
    ##     ,x = (SELECT x
    ##             FROM tempmultcatbasesources
    ##            WHERE tempmultcatbasesources.xtrsrc_id =
    ##                  multcatbasesources.xtrsrc_id
    ##          )
    ##     ,y = (SELECT y
    ##             FROM tempmultcatbasesources
    ##            WHERE tempmultcatbasesources.xtrsrc_id =
    ##                  multcatbasesources.xtrsrc_id
    ##          )
    ##     ,z = (SELECT z
    ##             FROM tempmultcatbasesources
    ##            WHERE tempmultcatbasesources.xtrsrc_id =
    ##                  multcatbasesources.xtrsrc_id
    ##          )
    ##     ,datapoints = (
    ##         SELECT datapoints
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##                   )
    ##     ,avg_weighted_ra = (
    ##         SELECT avg_weighted_ra
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##                        )
    ##     ,avg_weighted_decl = (
    ##         SELECT avg_weighted_decl
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##                          )
    ##     ,avg_ra_weight = (
    ##         SELECT avg_ra_weight
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##               multcatbasesources.xtrsrc_id
    ##                      )
    ##     ,avg_decl_weight = (
    ##         SELECT avg_decl_weight
    ##         FROM tempmultcatbasesources
    ##         WHERE tempmultcatbasesources.xtrsrc_id =
    ##         multcatbasesources.xtrsrc_id
    ##                        )
    ##WHERE EXISTS (
    ##    SELECT xtrsrc_id
    ##    FROM tempmultcatbasesources
    ##    WHERE tempmultcatbasesources.xtrsrc_id =
    ##    multcatbasesources.xtrsrc_id
    ##             )
    ##+--------------------------------------------

    try:
        cursor = conn.cursor()
        query = """\
        SELECT datapoints
              ,zone
              ,wm_ra
              ,wm_decl
              ,wm_ra_err
              ,wm_decl_err
              ,avg_wra
              ,avg_wdecl
              ,avg_weight_ra
              ,avg_weight_decl
              ,x
              ,y
              ,z
              ,catsrc_id
          FROM tempmergedcatalogs
        """
        cursor.execute(query)
        y = cursor.fetchall()
        query = """\
UPDATE mergedcatalogs
  SET datapoints = %s
     ,zone = %s
     ,wm_ra = %s
     ,wm_decl = %s
     ,wm_ra_err = %s
     ,wm_decl_err = %s
     ,avg_wra = %s
     ,avg_wdecl = %s
     ,avg_weight_ra = %s
     ,avg_weight_decl = %s
     ,x = %s
     ,y = %s
     ,z = %s
WHERE catsrc_id = %s
"""
        for k in range(len(y)):
            #print y[k][0], y[k][1], y[k][2]
            cursor.execute(query, (y[k][0]
                                  ,y[k][1]
                                  ,y[k][2]
                                  ,y[k][3]
                                  ,y[k][4]
                                  ,y[k][5]
                                  ,y[k][6]
                                  ,y[k][7]
                                  ,y[k][8]
                                  ,y[k][9]
                                  ,y[k][10]
                                  ,y[k][11] 
                                  ,y[k][12]
                                  ,y[k][13]
                                 ))
            if (k % 100 == 0):
                print "\t\tUpdate iter:", k
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _count_known_sources(conn, deRuiter_r):
    """Count number of extracted sources that are know in the running
    catalog"""

    try:
        cursor = conn.cursor()
        query = """\
SELECT COUNT(*)
  FROM selectedcatsources s0
      ,mergedcatalogs m0
 WHERE m0.zone BETWEEN s0.zone - cast(0.025 as integer)
                   AND s0.zone + cast(0.025 as integer)
   AND m0.wm_decl BETWEEN s0.decl - 0.025
                      AND s0.decl + 0.025
   AND m0.wm_ra BETWEEN s0.ra - alpha(0.025,s0.decl)
                    AND s0.ra + alpha(0.025,s0.decl)
   AND SQRT(  (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
            * (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
            / (s0.ra_err * s0.ra_err + m0.wm_ra_err * m0.wm_ra_err)
           + (s0.decl - m0.wm_decl) * (s0.decl - m0.wm_decl)
            / (s0.decl_err * s0.decl_err + m0.wm_decl_err * m0.wm_decl_err)
           ) < %s
"""
        cursor.execute(query, (deRuiter_r,))
        y = cursor.fetchall()
        print "\t\tNumber of known selectedcatsources (or sources in NOT IN): ", y[0][0]
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_new_assocs(conn, deRuiter_r):
    """Insert new associations for unknown sources

    This inserts new associations for the sources that were not known
    in the running catalogue (i.e. they did not have an entry in the
    runningcatalog table).
    """

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assoccrosscatsources
          (catsrc_id
          ,assoc_catsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT s1.catsrc_id as catsrc_id
                ,s1.catsrc_id as assoc_catsrc_id
                ,0
                ,0
                ,7
            FROM selectedcatsources s1
           WHERE s1.catsrc_id NOT IN (SELECT s0.catsrc_id
                                        FROM selectedcatsources s0
                                            ,mergedcatalogs m0
                                       WHERE m0.zone BETWEEN s0.zone - cast(0.025 as integer)
                                                         AND s0.zone + cast(0.025 as integer)
                                         AND m0.wm_decl BETWEEN s0.decl - 0.025
                                                            AND s0.decl + 0.025
                                         AND m0.wm_ra BETWEEN s0.ra - alpha(0.025,s0.decl)
                                                          AND s0.ra + alpha(0.025,s0.decl)
                                         AND SQRT(  (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
                                                  * (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
                                                  / (s0.ra_err * s0.ra_err + m0.wm_ra_err * m0.wm_ra_err)
                                                 + (s0.decl - m0.wm_decl) * (s0.decl - m0.wm_decl)
                                                  / (s0.decl_err * s0.decl_err + m0.wm_decl_err * m0.wm_decl_err)
                                                 ) < %s
                                     )
        """
        cursor.execute(query, (deRuiter_r,))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_new_source_mergedcatalogs(conn, cat_id, ra_min, ra_max, decl_min, decl_max, deRuiter_r):
    """Insert new sources into the running catalog"""

    try:
        cursor = conn.cursor()
        query = """\
INSERT INTO mergedcatalogs
  (catsrc_id
  ,datapoints
  ,zone
  ,wm_ra
  ,wm_decl
  ,wm_ra_err
  ,wm_decl_err
  ,avg_wra
  ,avg_wdecl
  ,avg_weight_ra
  ,avg_weight_decl
  ,x
  ,y
  ,z
  )
  SELECT s1.catsrc_id
        ,1
        ,s1.zone
        ,s1.ra
        ,s1.decl
        ,s1.ra_err
        ,s1.decl_err
        ,s1.ra / (s1.ra_err * s1.ra_err)
        ,s1.decl / (s1.decl_err * s1.decl_err)
        ,1 / (s1.ra_err * s1.ra_err)
        ,1 / (s1.decl_err * s1.decl_err)
        ,s1.x
        ,s1.y
        ,s1.z
    FROM selectedcatsources s1
   WHERE s1.cat_id = %s
     AND s1.catsrc_id NOT IN (SELECT s0.catsrc_id
                                FROM selectedcatsources s0
                                    ,mergedcatalogs m0
                               WHERE s0.cat_id = %s
                                 AND s0.zone BETWEEN CAST(FLOOR(CAST(%s AS DOUBLE) - 0.025) as INTEGER)
                                                 AND CAST(FLOOR(CAST(%s AS DOUBLE) + 0.025) as INTEGER)
                                 AND s0.decl BETWEEN CAST(%s AS DOUBLE) - 0.025
                                                 AND CAST(%s AS DOUBLE) + 0.025
                                 AND s0.ra BETWEEN CAST(%s AS DOUBLE) - alpha(0.025, %s)
                                               AND CAST(%s AS DOUBLE) + alpha(0.025, %s)
                                 AND m0.zone BETWEEN CAST(FLOOR(CAST(%s AS DOUBLE) - 0.025) as INTEGER)
                                                 AND CAST(FLOOR(CAST(%s AS DOUBLE) + 0.025) as INTEGER)
                                 AND m0.wm_decl BETWEEN CAST(%s AS DOUBLE) - 0.025
                                                    AND CAST(%s AS DOUBLE) + 0.025
                                 AND m0.wm_ra BETWEEN CAST(%s AS DOUBLE) - alpha(0.025, %s)
                                                  AND CAST(%s AS DOUBLE) + alpha(0.025, %s)
                                 AND m0.x * s0.x + m0.y * s0.y + m0.z * s0.z > COS(rad(0.025))
                                 AND SQRT(  (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
                                          * (s0.ra * COS(rad(s0.decl)) - m0.wm_ra * COS(rad(m0.wm_decl)))
                                          / (s0.ra_err * s0.ra_err + m0.wm_ra_err * m0.wm_ra_err)
                                         + (s0.decl - m0.wm_decl) * (s0.decl - m0.wm_decl)
                                          / (s0.decl_err * s0.decl_err + m0.wm_decl_err * m0.wm_decl_err)
                                         ) < %s
                            )
"""
        cursor.execute(query, (cat_id \
                              ,cat_id \
                              ,decl_min \
                              ,decl_max \
                              ,decl_min \
                              ,decl_max \
                              ,ra_min \
                              ,decl_max \
                              ,ra_max \
                              ,decl_max \
                              ,decl_min \
                              ,decl_max \
                              ,decl_min \
                              ,decl_max \
                              ,ra_min \
                              ,decl_max \
                              ,ra_max \
                              ,decl_max \
                              ,deRuiter_r \
                              ))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _update_fluxes_mergedcatalogs(conn, c):
    """ """

    try:
        cursor = conn.cursor()
        query = """\
        select a.catsrc_id
              ,a.assoc_catsrc_id
              ,c.catsrcid
              ,c.cat_id
              ,c.i_peak_avg
              ,c.i_peak_avg_err
              ,c.i_int_avg 
              ,c.i_int_avg_err
          from assoccrosscatsources a
              ,catalogedsources c 
         where a.assoc_catsrc_id = c.catsrcid 
           and c.cat_id = %s
        order by a.catsrc_id
        """
        for i in range(len(c)):
            print "c[", i, "] =", c[i]
            cursor.execute(query, (c[i],))
            results = zip(*cursor.fetchall())
            if len(results) != 0:
                catsrc_id = results[0]
                assoc_catsrc_id = results[1]
                catsrcid = results[2]
                cat_id = results[3]
                i_peak = results[4]
                i_peak_err = results[5]
                i_int = results[6]
                i_int_err = results[7]
                for j in range(len(catsrc_id)):
                    #print "catsrc_id[", j, "] =", catsrc_id[j] 
                    #      "\ni_peak[", j, "] =", i_peak[j] \
                    #      "\ni_int[", j, "] =", i_int[j]
                    if c[i] == 3:
                        uquery = """\
                        update mergedcatalogs
                           set i_peak_nvss = %s
                              ,i_peak_nvss_err = %s
                              ,i_int_nvss = %s
                              ,i_int_nvss_err = %s
                         where catsrc_id = %s
                        """
                    elif c[i] == 4:
                        uquery = """\
                        update mergedcatalogs
                           set i_peak_vlss = %s
                              ,i_peak_vlss_err = %s
                              ,i_int_vlss = %s
                              ,i_int_vlss_err = %s
                         where catsrc_id = %s
                        """
                    elif c[i] == 5:
                        uquery = """\
                        update mergedcatalogs
                           set i_peak_wenssm = %s
                              ,i_peak_wenssm_err = %s
                              ,i_int_wenssm = %s
                              ,i_int_wenssm_err = %s
                         where catsrc_id = %s
                        """
                    elif c[i] == 6:
                        uquery = """\
                        update mergedcatalogs
                           set i_peak_wenssp = %s
                              ,i_peak_wenssp_err = %s
                              ,i_int_wenssp = %s
                              ,i_int_wenssp_err = %s
                         where catsrc_id = %s
                        """
                    else:
                        logging.warn("No such catalogue %s for results %s" % c[i], catsrc_id[i])
                        raise
                    cursor.execute(uquery, (i_peak[j], i_peak_err[j], i_int[j], i_int_err[j], catsrc_id[j]))
                    conn.commit()
    except db.Error, e:
        logging.warn("Failed on query %s" % query)
        raise
    finally:
        cursor.close()

def _update_spectralindices_mergedcatalogs(conn, c):
    """ """

    queries = []
    v_wm_query = """\
    select catsrc_id
          ,i_int_vlss
          ,i_int_wenssm
      from mergedcatalogs 
     where i_int_vlss is not null 
       and i_int_wenssm is not null
    """
    queries.append(v_wm_query)
    v_wp_query = """\
    select catsrc_id
          ,i_int_vlss
          ,i_int_wenssp
      from mergedcatalogs 
     where i_int_vlss is not null 
       and i_int_wenssp is not null
    """
    queries.append(v_wp_query)
    v_n_query = """\
    select catsrc_id
          ,i_int_vlss
          ,i_int_nvss
      from mergedcatalogs 
     where i_int_vlss is not null 
       and i_int_nvss is not null
    """
    queries.append(v_n_query)
    wm_wp_query = """\
    select catsrc_id
          ,i_int_wenssm
          ,i_int_wenssp
      from mergedcatalogs 
     where i_int_wenssm is not null 
       and i_int_wenssp is not null
    """
    queries.append(wm_wp_query)
    wm_n_query = """\
    select catsrc_id
          ,i_int_wenssm
          ,i_int_nvss
      from mergedcatalogs 
     where i_int_wenssm is not null 
       and i_int_nvss is not null
    """
    queries.append(wm_n_query)
    wp_n_query = """\
    select catsrc_id
          ,i_int_wenssp
          ,i_int_nvss
      from mergedcatalogs 
     where i_int_wenssp is not null 
       and i_int_nvss is not null
    """
    queries.append(wp_n_query)
    v_wm_n_query = """\
    select catsrc_id
          ,i_int_vlss
          ,i_int_wenssm
          ,i_int_nvss
          ,i_int_vlss_err
          ,i_int_wenssm_err
          ,i_int_nvss_err
      from mergedcatalogs 
     where i_int_vlss is not null 
       and i_int_wenssm is not null
       and i_int_nvss is not null
    """
    queries.append(v_wm_n_query)
    try:
        cursor = conn.cursor()
        for i in range(len(queries)):
            cursor.execute(queries[i])
            results = zip(*cursor.fetchall())
            if len(results) != 0:
                if queries[i] == v_wm_n_query:
                    catsrc_id = results[0]
                    i_int1 = results[1]
                    i_int2 = results[2]
                    i_int3 = results[3]
                    i_int_err1 = results[4]
                    i_int_err2 = results[5]
                    i_int_err3 = results[6]
                else:
                    catsrc_id = results[0]
                    i_int1 = results[1]
                    i_int2 = results[2]
                if i == 0:
                    for j in range(len(catsrc_id)):
                        alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(74./325.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_v_wm = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(alpha), catsrc_id[j]))
                        conn.commit() 
                elif i == 1:
                    for j in range(len(catsrc_id)):
                        alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(74./352.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_v_wp = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(alpha), catsrc_id[j]))
                        conn.commit() 
                elif i == 2:
                    for j in range(len(catsrc_id)):
                        alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(74./1400.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_v_n = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(alpha), catsrc_id[j]))
                        conn.commit() 
                elif i == 3:
                    for j in range(len(catsrc_id)):
                        alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(325./352.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_wm_wp = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(alpha), catsrc_id[j]))
                        conn.commit() 
                elif i == 4:
                    for j in range(len(catsrc_id)):
                        alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(325./1400.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_wm_n = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(alpha), catsrc_id[j]))
                        conn.commit() 
                elif i == 5:
                    for j in range(len(catsrc_id)):
                        alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(352./1400.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_wp_n = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(alpha), catsrc_id[j]))
                        conn.commit() 
                elif i == 6:
                    for j in range(len(catsrc_id)):
                        # y = mx + c
                        # logS = m lognu + c
                        # Here we fit straight line through three points
                        nu = np.array([74E6, 325E6, 1400E6])
                        f = np.array([i_int1[j], i_int2[j], i_int3[j]])
                        f_e = np.array([i_int_err1[j], i_int_err2[j], i_int_err3[j]])
                        alpha, chisq = fitspectralindex(nu, f, f_e)
                        print "catsrc_id [", j, "] = ", catsrc_id[j], \
                              "\tspectral_index = ", -alpha, \
                              "\tchi_square = ", chisq
                        #alpha = -pylab.log10(i_int1[j]/i_int2[j]) / pylab.log10(352./1400.)
                        uquery = """\
                        update mergedcatalogs
                           set alpha_v_wm_n = %s
                              ,chisq_v_wm_n = %s
                         where catsrc_id = %s
                        """
                        cursor.execute(uquery, (float(-alpha), float(chisq), catsrc_id[j]))
                        conn.commit() 
    except db.Error, e:
        logging.warn("Failed on subuery %s" % uquery)
        logging.warn("Failed on query %s" % queries[i])
        raise
    finally:
        cursor.close()


def _select_variability_indices(conn, dsid, V_lim, eta_lim):
    """Select sources and variability indices in the running catalog"""

    try:
        cursor = conn.cursor()
        query = """\
SELECT xtrsrc_id
      ,ds_id
      ,datapoints
      ,wm_ra
      ,wm_decl
      ,wm_ra_err
      ,wm_decl_err
      ,sqrt(datapoints*(avg_I_peak_sq - avg_I_peak*avg_I_peak) /
            (datapoints-1)) / avg_I_peak as V
      ,(datapoints/(datapoints-1)) *
       (avg_weighted_I_peak_sq -
        avg_weighted_I_peak * avg_weighted_I_peak / avg_weight_peak)
       as eta
  FROM runningcatalog
 WHERE ds_id = %s
   AND datapoints > 1
   AND (sqrt(datapoints*(avg_I_peak_sq - avg_I_peak*avg_I_peak) /
             (datapoints-1)) / avg_I_peak > %s
        OR (datapoints/(datapoints-1)) *
            (avg_weighted_I_peak_sq -
             avg_weighted_I_peak * avg_weighted_I_peak /
             avg_weight_peak) > %s
       )
"""
        cursor.execute(query, (dsid, V_lim, eta_lim))
        y = cursor.fetchall()
        if len(y) > 0:
            print "Alert!"
        for i in range(len(y)):
            print "xtrsrc_id =", y[i][0]
            print "\tdatapoints =", y[i][2]
            print "\tv_nu =", y[i][7]
            print "\teta_nu =", y[i][8]
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query %s" % query)
        raise
    finally:
        cursor.close()


def variability_detection(conn, dsid, V_lim, eta_lim):
    """Detect variability in extracted sources compared to the previous
    detections"""

    #sources = _select_variability_indices(conn, dsid, V_lim, eta_lim)
    _select_variability_indices(conn, dsid, V_lim, eta_lim)


def associate_catalogued_sources_in_area(conn, ra, dec, search_radius):
    """Detection of variability in the extracted sources as
    compared their previous detections.
    """
    pass
    # the sources in the current image need to be matched to the
    # list of sources from the merged cross-correlated catalogues

def fitspectralindex(freq,flux,flux_err):

    powerlaw = lambda x, amp, index: amp * (x**index)
    
    xdata=pylab.array(freq)
    ydata=pylab.array(flux)
    yerr=pylab.array(flux_err)
    
    logx = pylab.log10(xdata)
    logy = pylab.log10(ydata)
    logyerr = yerr / ydata
    
    fitfunc = lambda p, x: p[0] + p[1] * x
    errfunc = lambda p, x, y, err: (y - fitfunc(p, x)) / err
    
    pinit=[flux[0],-0.7]
    out = optimize.leastsq(errfunc, pinit, args=(logx, logy, logyerr), full_output=1)
    
    pfinal = out[0]
    covar = out[1]
    #print "pfinal =", pfinal
    #print "covar =", covar
    
    index = pfinal[1]
    amp = 10.0**pfinal[0]
    
    #print "index =",index
    #print "amp =",amp
    
    indexErr = sqrt( covar[0][0] )
    ampErr = sqrt( covar[1][1] ) * amp
    
    chisq=0
    for i in range(len(freq)):
        chisq += ((flux[i] - amp*(freq[i]**index))/flux_err[i])**2
    
    """
    fig = pylab.figure()
    ax1 = fig.add_subplot(211)
    ax1.plot(xdata, amp*(xdata**index), 'b--', label='Fit')     # Fit
    ax1.errorbar(xdata, ydata, yerr=yerr, fmt='o', color='red', label='Data')  # Data
    for i in range(len(ax1.get_xticklabels())):
        ax1.get_xticklabels()[i].set_size('x-large')
    for i in range(len(ax1.get_yticklabels())):
        ax1.get_yticklabels()[i].set_size('x-large')
    ax1.set_xlabel(r'Frequency', size='x-large')
    ax1.set_ylabel(r'Flux', size='x-large')
    ax1.grid(True)

    ax2 = fig.add_subplot(212)
    ax2.loglog(xdata, xdata*amp*(xdata**index), 'b-', label='Fit')
    ax2.errorbar(xdata, xdata*ydata, yerr=yerr, fmt='o', color='red', label='Data')  # Data
    for i in range(len(ax2.get_xticklabels())):
        ax2.get_xticklabels()[i].set_size('x-large')
    for i in range(len(ax2.get_yticklabels())):
        ax2.get_yticklabels()[i].set_size('x-large')
    ax2.set_xlabel(r'Frequency (log)', size='x-large')
    ax2.set_ylabel(r'Flux (log)', size='x-large')
    ax2.grid(True)

    pylab.savefig('power_law_fit.png')
    """

    return index,chisq


