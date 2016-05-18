/*
 * policy.c - functions that encapsulate the notion of a policy
 * Copyright (c) 2016 Red Hat Inc., Durham, North Carolina.
 * All Rights Reserved. 
 *
 * This software may be freely redistributed and/or modified under the
 * terms of the GNU General Public License as published by the Free
 * Software Foundation; either version 2, or (at your option) any
 * later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; see the file COPYING. If not, write to the
 * Free Software Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 *
 * Authors:
 *   Steve Grubb <sgrubb@redhat.com>
 */

#include "config.h"
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <strings.h>
#include <limits.h>
#include <stdlib.h>
#include "file.h"
#include "rules.h"
#include "policy.h"
#include "nv.h"
#include "message.h"

static llist rules;

static const nv_t table[] = {
{       NO_OPINION, "no-opinion" },
{       ALLOW, "allow" },
{       DENY, "deny" },
{       ALLOW_AUDIT, "allow_audit" },
{       DENY_AUDIT, "deny_audit" }
};

#define MAX_DECISIONS (sizeof(table)/sizeof(table[0]))

int dec_name_to_val(const char *name)
{
        unsigned int i = 0;
        while (i < MAX_DECISIONS) {
                if (strcasecmp(name, table[i].name) == 0)
                        return table[i].value;
                i++;
        }
        return -1;
}

const char *dec_val_to_name(unsigned int v)
{
	unsigned int i = 0;
        while (i < MAX_DECISIONS) {
		if (v == table[i].value)
	                return table[i].name;
		i++;
	}
        return NULL;
}

static char *get_line(FILE *f, char *buf)
{
	if (fgets_unlocked(buf, 128, f)) {
		/* remove newline */
		char *ptr = strchr(buf, 0x0a);
		if (ptr)
			*ptr = 0;
		return buf;
	}
	return NULL;
}

// Returns 0 on success and 1 on error
int load_config(void)
{
	int fd, lineno = 1;
	FILE *f;
	char buf[PATH_MAX+1];

	rules_create(&rules);

	// Now open the file and load them one by one.
	fd = open(CONFIG_FILE, O_NOFOLLOW|O_RDONLY);
	if (fd < 0) {
		msg(LOG_ERR, "Error opening config (%s)",
			strerror(errno));
		return 1;
	}

	f = fdopen(fd, "r");
	if (f == NULL) {
		msg(LOG_ERR, "Error - fdopen failed (%s)",
			strerror(errno));
		return 1;
	}

	while (get_line(f, buf)) {
		int rc = rules_append(&rules, buf, lineno);
		if (rc) {
			fclose(f);
			return 1;
		}
		lineno++;
	}
	fclose(f);

	if (rules.cnt == 0) {
		msg(LOG_INFO, "No rules in config - exiting");
		return 1;
	}
	return 0;
}

int reload_config(void)
{
	destroy_config();
	return load_config();
}

static void log_it(unsigned int num, decision_t results, event_t *e)
{
	subject_attr_t *subj, *subj2, *subj3;
	//subject_attr_t *subj4;
	object_attr_t *obj;
	//object_attr_t *obj2;

	subj = get_subj_attr(e, EXE);
	subj2 = get_subj_attr(e, AUID);
	subj3 = get_subj_attr(e, PID);
	//subj4 = get_subj_attr(e, EXE_DIR);
	obj = get_obj_attr(e, PATH);
	//obj2 = get_obj_attr(e, SHA256HASH);
	msg(LOG_DEBUG, "rule:%u dec=%s auid=%d pid=%d exe=%s file=%s",
		num+1,
		dec_val_to_name(results),
		subj2->val, subj3->val, subj->str,
		obj->o);
}

decision_t process_event(event_t *e)
{
	decision_t results = NO_OPINION;

	/* populate the event struct and iterate over the rules */
	rules_first(&rules);
	lnode *r = rules_get_cur(&rules);
	while (r) {
		results = rule_evaluate(r, e);
		// If a rule has an opinion, stop and use it
		if (results != NO_OPINION)
			break;
		r = rules_next(&rules);
	}

	// Output some information if debugging on
	if ((debug > 1 && results == DENY) || (debug == 1))
		log_it(r->num, results, e);

	// If we are not in permissive mode, return any decision
	if (results != NO_OPINION)
		return results & ~AUDIT;

	return ALLOW;
}

void destroy_config(void)
{
	rules_clear(&rules);
}
