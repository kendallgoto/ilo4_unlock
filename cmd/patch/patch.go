//  This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
//  Copyright (c) 2024 Kendall Goto.
//
//  This program is free software: you can redistribute it and/or modify
//  it under the terms of the GNU General Public License as published by
//  the Free Software Foundation, version 3.
//
//  This program is distributed in the hope that it will be useful, but
//  WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
//  General Public License for more details.
//
//  You should have received a copy of the GNU General Public License
//  along with this program. If not, see <http://www.gnu.org/licenses/>.

package patch

import (
	"github.com/davecgh/go-spew/spew"
	"github.com/kendallgoto/ilo4_unlock/pkg/config"
	cli "github.com/urfave/cli/v2"
)

func doPatch(cCtx *cli.Context, patch config.PatchDef) error {
	spew.Dump(patch)
	return nil
}

func AddPatchCommands(base *cli.Command) {
	config.Patches["default"] = config.Patches[config.Default]
	for name, patch := range config.Patches {
		base.Subcommands = append(base.Subcommands, &cli.Command{
			Name:  name,
			Usage: patch.Description,
			Action: func(cCtx *cli.Context) error {
				return doPatch(cCtx, patch)
			},
		})
	}
}
func Command() *cli.Command {
	return &cli.Command{
		Name:        "patch",
		Usage:       "build a given patch",
		Subcommands: []*cli.Command{},
		Action: func(cCtx *cli.Context) error {
			return doPatch(cCtx, config.Patches[config.Default])
		},
	}
}
